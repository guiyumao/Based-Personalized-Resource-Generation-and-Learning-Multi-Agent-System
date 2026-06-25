"""Async evaluation service backed by real answer records."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Any

from langchain_core.messages import SystemMessage
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import SessionLocal
from common.messaging.rabbitmq import RabbitMQPublisher
from common.models.learning import AnswerRecord, Exercise, KnowledgePoint, LearningReport, User, UserProfile
from services.agent_service.app.services.llm_factory import LLMFactory
from services.evaluation_service.app.schemas.report import (
    AnalyticsSuggestion,
    AnswerEvaluationResult,
    AnswerRecordIn,
    AnswerRecordSubmission,
    BatchAnswerSubmission,
    BatchEvaluationResponse,
    KnowledgePointFeedback,
    KnowledgePointStageStatus,
    LatestMistakeEvidence,
    MistakeItem,
    MistakeNotebook,
    MistakeNotebookClearResult,
    MonthlyReportResponse,
    PracticeFeedback,
    PracticeSubmission,
    QAMistakeSubmission,
    RemedialExerciseItem,
    RemedialExerciseSet,
    ReportDetail,
    ReportEvidence,
    ReportSummary,
    StageReportResponse,
    compatibility_question_type,
    normalize_difficulty,
    normalize_exercise_type,
)
from services.evaluation_service.app.services.profile_updater import LearnerProfileUpdater

logger = logging.getLogger(__name__)

SUBJECTIVE_SCORING_PROMPT = """你是一位严格的评分老师。请根据以下标准答案和评分要点，对学生的回答进行评分。

题目内容：{exercise_content}
标准答案 / 评分要点：{reference_answer}
满分：{max_score}
学生回答：{user_answer}

请给出：
1. 评分 (0 ~ {max_score})。
2. 简短评语 (20字以内)。
3. 修改建议 (如果有错误)。

输出 JSON 格式：{{"score": number, "comment": "string", "suggestion": "string"}}"""

STAGE_REPORT_PROMPT = """你是一位学习分析师。请根据以下学习数据生成一份个性化阶段报告。

学生姓名：{student_name}
学习周期：{start_date} 到 {end_date}
章节：{chapter_name}
知识点掌握情况：
{knowledge_points_status}
薄弱知识点 Top 3：{weak_points}
答题总数：{total_answers}，正确率：{overall_accuracy}%
学习时长：{total_time}

报告要求：
1. 总体评语（30~50字，鼓励性）。
2. 针对薄弱知识点的具体学习建议（看哪个课件、做哪些题）。
3. 下一步学习优先级排序（列出3个知识点）。

输出纯文本，段落间空一行。"""

MONTHLY_REPORT_PROMPT = """你是一位资深教育顾问。请根据学生过去一个月的学习历程，写一份综合学习评语。

学生：{student_name}
月度完成章节数：{chapters_completed}
整体正确率变化：{accuracy_trend}
进步最大的知识点：{most_improved}
仍需加强的知识点：{still_weak}
平均每日学习时长：{avg_daily_time}

评语要求：
- 语气温暖而专业，肯定进步，指出可提升空间。
- 给出一个核心建议（一句话）。
- 字数控制在80字以内。

输出纯文本。"""

MAX_TIME_RULES: dict[str, dict[str, float]] = {
    "choice": {"basic": 60.0, "intermediate": 90.0, "advanced": 120.0},
    "fill": {"basic": 90.0, "intermediate": 120.0, "advanced": 180.0},
    "judge": {"basic": 45.0, "intermediate": 60.0, "advanced": 90.0},
    "short_answer": {"basic": 240.0, "intermediate": 360.0, "advanced": 480.0},
    "code": {"basic": 600.0, "intermediate": 900.0, "advanced": 1200.0},
}
SUBJECTIVE_CORRECT_THRESHOLD = 0.6
PROFILE_UPDATE_QUEUE = "profile_updates"
PATH_ADJUSTMENT_QUEUE = "path_adjustments"


@dataclass(slots=True)
class PreparedSubmission:
    """Normalized submission context before scoring."""

    user_id_int: int
    user_id_str: str
    student_name: str
    exercise_id_int: int
    exercise_id_str: str
    user_answer: str
    knowledge_point_ids: list[str]
    exercise_type: str
    difficulty: str
    standard_answer: str | None
    reference_answer: str | None
    max_score: float
    exercise_content: str
    explanation: str
    chapter_id: str | None
    chapter_name: str | None
    time_spent: float
    max_time: float


@dataclass(slots=True)
class EvaluationOutcome:
    """Scoring outcome before persistence."""

    is_correct: bool
    score: float
    max_score: float
    ratio: float
    comment: str
    suggestion: str
    encouragement: str
    error_pattern: str
    llm_used: bool


@dataclass(slots=True)
class AnswerTrace:
    """Normalized persisted answer trace used for reporting."""

    answer_record_id: int
    user_id: int
    exercise_id: int
    exercise_id_str: str
    knowledge_point_ids: list[str]
    question_type: str
    difficulty: str
    chapter_id: str | None
    chapter_name: str | None
    user_answer: str
    correct_answer: str
    reference_answer: str | None
    explanation: str
    is_correct: bool
    score: float
    max_score: float
    ratio: float
    time_spent: float
    error_pattern: str
    suggestion: str
    comment: str
    prompt: str
    options: str
    created_at: datetime


class EvaluationLLMClient:
    """Thin async wrapper around the configured OpenAI-compatible chat model."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._factory = LLMFactory(self._settings)

    async def score_subjective(
        self,
        *,
        exercise_content: str,
        reference_answer: str,
        max_score: float,
        user_answer: str,
    ) -> dict[str, Any]:
        prompt = SUBJECTIVE_SCORING_PROMPT.format(
            exercise_content=exercise_content,
            reference_answer=reference_answer,
            max_score=max_score,
            user_answer=user_answer,
        )
        message = await self._invoke(prompt, temperature=0.0)
        payload = self._parse_json_payload(message)
        return {
            "score": max(0.0, min(float(payload["score"]), max_score)),
            "comment": str(payload["comment"]).strip(),
            "suggestion": str(payload["suggestion"]).strip(),
        }

    async def generate_stage_report(self, **prompt_values: Any) -> str:
        prompt = STAGE_REPORT_PROMPT.format(**prompt_values)
        return (await self._invoke(prompt, temperature=0.3)).strip()

    async def generate_monthly_report(self, **prompt_values: Any) -> str:
        prompt = MONTHLY_REPORT_PROMPT.format(**prompt_values)
        return (await self._invoke(prompt, temperature=0.4)).strip()

    async def _invoke(self, prompt: str, *, temperature: float) -> str:
        model = await asyncio.to_thread(self._factory.build_chat_model, temperature)
        response = await model.ainvoke([SystemMessage(content=prompt)])
        content = getattr(response, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    def _parse_json_payload(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1)
        elif cleaned and not cleaned.startswith("{"):
            matched = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if matched:
                cleaned = matched.group(1)
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("LLM score response must be a JSON object.")
        for required in ("score", "comment", "suggestion"):
            if required not in payload:
                raise ValueError(f"Missing field '{required}' in LLM score response.")
        return payload


class ReportService:
    """Evaluation and report service using persisted answer data."""

    def __init__(
        self,
        *,
        session_factory: Any = SessionLocal,
        llm_client: EvaluationLLMClient | None = None,
        publisher: RabbitMQPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._llm_client = llm_client or EvaluationLLMClient()
        self._publisher = publisher or RabbitMQPublisher()
        self._profile_updater = LearnerProfileUpdater()

    async def submit_answer(self, payload: AnswerRecordSubmission) -> AnswerEvaluationResult:
        """Evaluate one answer submission and persist all real outputs."""

        prepared = await asyncio.to_thread(self._prepare_submission, payload)
        outcome = await self._evaluate_submission(prepared)
        result, events = await asyncio.to_thread(self._persist_submission, prepared, outcome)
        await self._publish_events(events)
        return result

    async def batch_submit(self, payload: BatchAnswerSubmission) -> BatchEvaluationResponse:
        """Evaluate a batch of answer submissions."""

        results: list[AnswerEvaluationResult] = []
        for record in payload.records:
            results.append(await self.submit_answer(record))
        correct_count = sum(1 for item in results if item.is_correct)
        accuracy = round((correct_count / len(results)) * 100, 2) if results else 0.0
        return BatchEvaluationResponse(
            results=results,
            total_submissions=len(results),
            correct_submissions=correct_count,
            accuracy=accuracy,
        )

    async def generate_stage_report(self, user_id: str, chapter_id: str) -> StageReportResponse:
        """Generate one chapter report from real answer records."""

        user_id_int = await asyncio.to_thread(self._normalize_user_id, user_id)
        traces, profile, student_name = await asyncio.to_thread(
            self._load_user_context,
            user_id_int,
        )
        chapter_traces = [item for item in traces if item.chapter_id == chapter_id]
        if not chapter_traces:
            raise ValueError(f"No answer records found for chapter '{chapter_id}'.")

        chapter_name = next(
            (item.chapter_name for item in reversed(chapter_traces) if item.chapter_name),
            chapter_id,
        )
        kp_statuses = self._build_stage_statuses(chapter_traces, profile)
        weak_points = [item.knowledge_point_id for item in kp_statuses if item.weak][:3]
        if not weak_points:
            weak_points = [item.knowledge_point_id for item in kp_statuses[:3]]

        start_date = min(item.created_at for item in chapter_traces)
        end_date = max(item.created_at for item in chapter_traces)
        overall_accuracy = round(
            (sum(1 for item in chapter_traces if item.is_correct) / len(chapter_traces)) * 100,
            2,
        )
        total_time = round(sum(item.time_spent for item in chapter_traces), 2)
        knowledge_points_status = "\n".join(
            (
                f"- {item.knowledge_point_id}：掌握度{item.mastery_score:.2f}，"
                f"正确率{item.accuracy:.2f}%"
            )
            for item in kp_statuses
        )
        report_text = await self._llm_client.generate_stage_report(
            student_name=student_name,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            chapter_name=chapter_name,
            knowledge_points_status=knowledge_points_status,
            weak_points="、".join(weak_points) if weak_points else "无",
            total_answers=len(chapter_traces),
            overall_accuracy=overall_accuracy,
            total_time=f"{total_time:.2f} 秒",
        )
        response = StageReportResponse(
            user_id=str(user_id_int),
            chapter_id=chapter_id,
            chapter_name=chapter_name,
            generated_at=datetime.now(UTC),
            overall_accuracy=overall_accuracy,
            total_answers=len(chapter_traces),
            total_time_spent=total_time,
            top_weak_points=weak_points,
            knowledge_points=kp_statuses,
            report_text=report_text,
            suggested_next_focus=[item.knowledge_point_id for item in kp_statuses[:3]],
        )
        await asyncio.to_thread(self._save_report, user_id_int, "stage", response.model_dump(mode="json"))
        return response

    async def generate_monthly_report(self, user_id: str) -> MonthlyReportResponse:
        """Generate one rolling 30-day monthly report."""

        user_id_int = await asyncio.to_thread(self._normalize_user_id, user_id)
        traces, profile, student_name = await asyncio.to_thread(
            self._load_user_context,
            user_id_int,
        )
        now = datetime.now(UTC)
        start = now - timedelta(days=30)
        month_traces = [item for item in traces if item.created_at >= start]
        if not month_traces:
            raise ValueError("No answer records found in the past 30 days.")

        chapter_ids = {item.chapter_id for item in month_traces if item.chapter_id}
        overall_accuracy = round(
            (sum(1 for item in month_traces if item.is_correct) / len(month_traces)) * 100,
            2,
        )
        day_buckets: dict[str, float] = defaultdict(float)
        for item in month_traces:
            day_buckets[item.created_at.date().isoformat()] += item.time_spent
        avg_daily_time = round(sum(day_buckets.values()) / len(day_buckets), 2) if day_buckets else 0.0

        first_half_end = start + timedelta(days=15)
        first_half = [item for item in month_traces if item.created_at < first_half_end]
        second_half = [item for item in month_traces if item.created_at >= first_half_end]
        first_accuracy = self._calculate_accuracy(first_half)
        second_accuracy = self._calculate_accuracy(second_half)
        accuracy_trend = f"{first_accuracy:.2f}% -> {second_accuracy:.2f}%"
        most_improved = self._find_most_improved(month_traces, start, first_half_end)
        still_weak = self._find_still_weak(month_traces, profile)
        report_text = await self._llm_client.generate_monthly_report(
            student_name=student_name,
            chapters_completed=len(chapter_ids),
            accuracy_trend=accuracy_trend,
            most_improved=most_improved or "暂无明显领先知识点",
            still_weak="、".join(still_weak) if still_weak else "暂无",
            avg_daily_time=f"{avg_daily_time:.2f} 秒",
        )
        response = MonthlyReportResponse(
            user_id=str(user_id_int),
            generated_at=now,
            start_date=start,
            end_date=now,
            chapters_completed=len(chapter_ids),
            overall_accuracy=overall_accuracy,
            avg_daily_time=avg_daily_time,
            most_improved=most_improved,
            still_weak=still_weak,
            summary_text=report_text,
        )
        await asyncio.to_thread(
            self._save_report,
            user_id_int,
            "monthly",
            response.model_dump(mode="json"),
        )
        return response

    async def submit_legacy_answer(self, payload: AnswerRecordIn) -> AnswerEvaluationResult:
        """Compatibility wrapper for the old `/answers` endpoint."""

        submission = AnswerRecordSubmission(
            user_id=str(payload.user_id),
            exercise_id=str(payload.exercise_id),
            user_answer=payload.answer,
            is_correct=payload.is_correct,
            time_spent=float(payload.time_spent),
            knowledge_point_ids=[],
            exercise_type="choice",
            difficulty="intermediate",
        )
        return await self.submit_answer(submission)

    async def evaluate_practice(self, payload: PracticeSubmission) -> PracticeFeedback:
        """Compatibility wrapper for the student practice endpoint."""

        normalized_type = normalize_exercise_type(payload.question_type)
        reference_answer = payload.reference_answer or payload.correct_answer
        max_score = payload.max_score or (100.0 if normalized_type in {"short_answer", "code"} else None)
        exercise_content = payload.exercise_content or payload.analysis

        result = await self.submit_answer(
            AnswerRecordSubmission(
                user_id=str(payload.user_id),
                exercise_id=str(payload.exercise_id),
                user_answer=payload.user_answer,
                time_spent=float(payload.time_spent),
                knowledge_point_ids=[payload.knowledge_point],
                exercise_type=payload.question_type,
                difficulty=payload.difficulty,
                standard_answer=payload.correct_answer,
                reference_answer=reference_answer if normalized_type in {"short_answer", "code"} else None,
                max_score=max_score,
                exercise_content=exercise_content,
                explanation=payload.analysis,
                chapter_id=payload.chapter_id,
                chapter_name=payload.chapter_name,
            )
        )
        mastery = result.knowledge_points[0].mastery_score if result.knowledge_points else None
        return PracticeFeedback(
            user_id=payload.user_id,
            exercise_id=payload.exercise_id,
            is_correct=result.is_correct,
            score=round((result.score / result.max_score) * 100),
            feedback=result.comment,
            suggested_action=result.suggestion,
            analysis=result.explanation or "",
            mastery_after_update=int(round(mastery)) if mastery is not None else None,
        )

    async def record_qa_mistake(self, payload: QAMistakeSubmission) -> MistakeItem:
        """Persist one QA mistake using the same real evaluation pipeline."""

        result = await self.submit_answer(
            AnswerRecordSubmission(
                user_id=str(payload.user_id),
                exercise_id=str(payload.exercise_id),
                user_answer=payload.wrong_answer,
                time_spent=float(payload.time_spent),
                knowledge_point_ids=[payload.knowledge_point],
                exercise_type=payload.question_type,
                difficulty=payload.difficulty,
                standard_answer=payload.correct_answer,
                reference_answer=payload.correct_answer
                if normalize_exercise_type(payload.question_type) in {"short_answer", "code"}
                else None,
                max_score=100.0
                if normalize_exercise_type(payload.question_type) in {"short_answer", "code"}
                else None,
                exercise_content=payload.question_summary,
                explanation=payload.analysis,
                chapter_id=payload.chapter_id,
                chapter_name=payload.chapter_name,
            )
        )
        return MistakeItem(
            user_id=payload.user_id,
            exercise_id=payload.exercise_id,
            knowledge_point=payload.knowledge_point,
            question_type=compatibility_question_type(normalize_exercise_type(payload.question_type)),
            prompt=payload.question or "",
            user_answer=payload.wrong_answer,
            correct_answer=payload.correct_answer,
            analysis=payload.analysis,
            suggested_action=result.suggestion or payload.suggested_action,
        )

    async def generate_stage_report_summary_legacy(self, user_id: int) -> ReportSummary:
        """Compatibility stage summary for existing callers."""

        traces, _, _ = await asyncio.to_thread(self._load_user_context, user_id)
        chapter_id = self._latest_chapter_id(traces)
        if chapter_id is None:
            raise ValueError("No chapter-linked answer data found.")
        report = await self.generate_stage_report(str(user_id), chapter_id)
        return ReportSummary(
            report_type="stage",
            user_id=user_id,
            title=f"{report.chapter_name} 阶段报告",
            summary=report.report_text.splitlines()[0] if report.report_text else "",
        )

    async def generate_stage_report_detail(self, user_id: int) -> ReportDetail:
        """Compatibility detailed stage report."""

        traces, profile, _ = await asyncio.to_thread(self._load_user_context, user_id)
        chapter_id = self._latest_chapter_id(traces)
        chapter_traces = self._select_latest_stage_traces(traces, chapter_id)
        if not chapter_traces:
            return self._empty_detail(user_id, "stage", "阶段报告")
        evidence = self._build_evidence(chapter_traces)
        statuses = self._build_stage_statuses(chapter_traces, profile)
        strengths = [f"本章节共完成 {len(chapter_traces)} 次答题，正确率 {evidence.accuracy}%"]
        if evidence.strongest_question_types:
            strengths.append(f"表现较稳的题型：{'、'.join(evidence.strongest_question_types[:3])}")
        weaknesses = []
        if evidence.weakest_knowledge_point:
            weaknesses.append(
                f"当前最薄弱知识点是 {evidence.weakest_knowledge_point}，正确率 {evidence.weakest_knowledge_accuracy}%"
            )
        weak_points = [item.knowledge_point_id for item in statuses if item.weak][:3]
        if weak_points:
            weaknesses.append(f"连续错题或近十题正确率偏低的知识点：{'、'.join(weak_points)}")
        next_actions = [f"优先复习 {item.knowledge_point_id}" for item in statuses[:3]]
        return ReportDetail(
            report_type="stage",
            user_id=user_id,
            title="阶段学习报告",
            summary=f"最近章节正确率 {evidence.accuracy}%，平均用时 {evidence.average_time_spent} 秒。",
            strengths=strengths,
            weaknesses=weaknesses or ["暂未发现集中性弱点。"],
            next_actions=next_actions or ["继续完成真实练习，积累更多评估数据。"],
            evidence=evidence,
        )

    async def generate_comprehensive_report(self, user_id: int) -> ReportSummary:
        """Compatibility monthly summary."""

        report = await self.generate_monthly_report(str(user_id))
        return ReportSummary(
            report_type="monthly",
            user_id=user_id,
            title="月度综合报告",
            summary=report.summary_text,
        )

    async def generate_comprehensive_report_detail(self, user_id: int) -> ReportDetail:
        """Compatibility monthly detail report."""

        traces, profile, _ = await asyncio.to_thread(self._load_user_context, user_id)
        now = datetime.now(UTC)
        start = now - timedelta(days=30)
        month_traces = [item for item in traces if item.created_at >= start]
        if not month_traces:
            return self._empty_detail(user_id, "comprehensive", "月度综合报告")

        evidence = self._build_evidence(month_traces)
        weak_points = self._find_still_weak(month_traces, profile)
        strengths = [f"过去 30 天共完成 {len(month_traces)} 次答题，正确率 {evidence.accuracy}%"]
        weaknesses = [f"仍需重点加强：{'、'.join(weak_points)}"] if weak_points else ["暂无持续性薄弱点。"]
        next_actions = [f"下一阶段优先处理 {item}" for item in weak_points[:3]]
        if not next_actions:
            next_actions = ["保持当前节奏，逐步增加进阶题比例。"]
        return ReportDetail(
            report_type="comprehensive",
            user_id=user_id,
            title="月度综合报告",
            summary=f"近 30 天平均得分 {evidence.average_score}，平均单题用时 {evidence.average_time_spent} 秒。",
            strengths=strengths,
            weaknesses=weaknesses,
            next_actions=next_actions,
            evidence=evidence,
        )

    async def get_mistake_statistics(self, user_id: int) -> dict[str, object]:
        """Return mistake statistics from persisted answer history."""

        notebook = await self.get_mistake_notebook(user_id)
        return {
            "user_id": user_id,
            "mistake_count": notebook.mistake_count,
            "exercise_ids": [item.exercise_id for item in notebook.items],
        }

    async def get_mistake_notebook(self, user_id: int) -> MistakeNotebook:
        """Return the learner mistake notebook."""

        traces, profile, _ = await asyncio.to_thread(self._load_user_context, user_id)
        wrong_traces = self._filter_active_mistake_traces(traces, profile)
        items = [
            MistakeItem(
                user_id=user_id,
                exercise_id=item.exercise_id,
                knowledge_point=item.knowledge_point_ids[0] if item.knowledge_point_ids else "unknown",
                question_type=compatibility_question_type(item.question_type),
                prompt=getattr(item, "prompt", "") or "",
                options=getattr(item, "options", "") or "",
                user_answer=item.user_answer,
                correct_answer=item.correct_answer,
                analysis=item.explanation,
                suggested_action=item.suggestion or "回看解析后再做同类题。",
            )
            for item in wrong_traces
        ]
        return MistakeNotebook(user_id=user_id, mistake_count=len(items), items=items)

    async def get_teacher_mistake_notebook(self, user_id: int) -> MistakeNotebook:
        """Return all persisted mistakes for teacher review."""

        traces, _, _ = await asyncio.to_thread(self._load_user_context, user_id)
        wrong_traces = [item for item in traces if not item.is_correct]
        items = [
            MistakeItem(
                user_id=user_id,
                exercise_id=item.exercise_id,
                knowledge_point=item.knowledge_point_ids[0] if item.knowledge_point_ids else "unknown",
                question_type=compatibility_question_type(item.question_type),
                prompt=getattr(item, "prompt", "") or "",
                options=getattr(item, "options", "") or "",
                user_answer=item.user_answer,
                correct_answer=item.correct_answer,
                analysis=item.explanation,
                suggested_action=item.suggestion or "回看解析后再做同类题。",
            )
            for item in wrong_traces
        ]
        return MistakeNotebook(user_id=user_id, mistake_count=len(items), items=items)

    async def clear_mistake_notebook(self, user_id: int) -> MistakeNotebookClearResult:
        """Hide the learner's current mistake notebook entries from future notebook reads."""

        return await asyncio.to_thread(self._clear_mistake_notebook, user_id)

    async def generate_remedial_exercises(self, user_id: int) -> RemedialExerciseSet:
        """Generate deterministic remedial exercises from real mistakes."""

        notebook = await self.get_mistake_notebook(user_id)
        exercises: list[RemedialExerciseItem] = []
        for index, item in enumerate(notebook.items, start=1):
            prompt = (
                f"围绕知识点 {item.knowledge_point} 再做一题，重点修正上次暴露的错误："
                f"{item.analysis or item.suggested_action}"
            )
            exercises.append(
                RemedialExerciseItem(
                    exercise_id=900000 + index,
                    knowledge_point=item.knowledge_point,
                    question_type=item.question_type,
                    prompt=prompt,
                    options=[],
                    answer=item.correct_answer,
                    analysis=f"本题源自真实错题 {item.exercise_id} 的定向补练。",
                    source_exercise_id=item.exercise_id,
                )
            )
        return RemedialExerciseSet(
            user_id=user_id,
            generated_from_mistakes=len(exercises),
            summary="已根据真实错题记录生成补练建议。",
            exercises=exercises,
        )

    async def generate_profile_snapshot(self, user_id: int) -> dict[str, object]:
        """Return a learner dashboard snapshot using only persisted data."""

        traces, profile, _ = await asyncio.to_thread(self._load_user_context, user_id)
        mastery_json = profile.mastery_json if isinstance(profile.mastery_json, dict) else {}
        mastery_values = [
            float(value.get("score", 0))
            for value in mastery_json.values()
            if isinstance(value, dict)
        ]
        mastery_overview = round(mean(mastery_values), 2) if mastery_values else 0.0
        total_time = sum(item.time_spent for item in traces)
        answered_days = {item.created_at.date().isoformat() for item in traces}
        avg_time = round(total_time / len(traces), 2) if traces else 0.0
        weak_points = [key for key, value in mastery_json.items() if isinstance(value, dict) and value.get("weak")]
        has_learning_activity = bool(traces or mastery_values)
        learning_style = profile.learning_style if profile.learning_style and profile.learning_style.upper() != "VARK" else ""
        return {
            "user_id": user_id,
            "learning_style": learning_style,
            "mastery_overview": mastery_overview,
            "weekly_focus_minutes": round((total_time / 60.0), 2),
            "habit_summary": (
                f"累计答题 {len(traces)} 次，活跃学习 {len(answered_days)} 天，平均每题 {avg_time:.2f} 秒。"
                if has_learning_activity
                else ""
            ),
            "radar_metrics": [
                {"dimension": "知识掌握", "score": round(mastery_overview)},
                {"dimension": "答题准确", "score": round(self._calculate_accuracy(traces))},
                {"dimension": "用时稳定", "score": max(0, round(100 - min(avg_time, 100)))},
                {"dimension": "薄弱点控制", "score": max(0, 100 - (len(weak_points) * 15))},
                {"dimension": "学习持续性", "score": min(100, len(answered_days) * 10)},
            ] if has_learning_activity else [],
            "heatmap": [
                {
                    "knowledge_point": key,
                    "mastery": round(float(value.get("score", 0)), 2),
                }
                for key, value in mastery_json.items()
                if isinstance(value, dict)
            ][:12],
        }

    async def generate_learning_suggestions(self, user_id: int) -> AnalyticsSuggestion:
        """Return personalized suggestions distilled from real traces."""

        traces, profile, _ = await asyncio.to_thread(self._load_user_context, user_id)
        weak_points = self._find_still_weak(traces, profile)
        avg_time = round(sum(item.time_spent for item in traces) / len(traces), 2) if traces else 0.0
        suggestions: list[str] = []
        if not traces and not profile.mastery_json:
            return AnalyticsSuggestion(
                user_id=user_id,
                suggestions=[],
                focus_areas=[],
                recommended_action="",
            )
        if weak_points:
            suggestions.append(f"优先围绕 {weak_points[0]} 做定向复习和专项训练。")
        if avg_time > 180:
            suggestions.append("主观题平均用时偏长，建议先做拆步练习再限时训练。")
        wrong_types = Counter(item.question_type for item in traces if not item.is_correct)
        if wrong_types:
            suggestions.append(f"最近失分最多的题型是 {compatibility_question_type(wrong_types.most_common(1)[0][0])}。")
        if not suggestions:
            suggestions.append("当前表现较稳，可以逐步增加进阶题和综合题占比。")
        focus_areas = weak_points[:3]
        recommended_action = (
            f"下一步先处理 {focus_areas[0]}，再回到学习路径继续推进。"
            if focus_areas
            else "下一步继续保持当前节奏，积累更多真实答题记录。"
        )
        return AnalyticsSuggestion(
            user_id=user_id,
            suggestions=suggestions,
            focus_areas=focus_areas,
            recommended_action=recommended_action,
        )

    async def _evaluate_submission(self, prepared: PreparedSubmission) -> EvaluationOutcome:
        normalized_type = normalize_exercise_type(prepared.exercise_type)
        if normalized_type in {"short_answer", "code"}:
            result = await self._llm_client.score_subjective(
                exercise_content=prepared.exercise_content,
                reference_answer=prepared.reference_answer or "",
                max_score=prepared.max_score,
                user_answer=prepared.user_answer,
            )
            score = max(0.0, min(float(result["score"]), prepared.max_score))
            ratio = round(score / prepared.max_score, 4) if prepared.max_score else 0.0
            is_correct = ratio >= SUBJECTIVE_CORRECT_THRESHOLD
            error_pattern = self._detect_error_pattern(
                prepared=prepared,
                is_correct=is_correct,
                ratio=ratio,
            )
            return EvaluationOutcome(
                is_correct=is_correct,
                score=score,
                max_score=prepared.max_score,
                ratio=ratio,
                comment=str(result["comment"]).strip(),
                suggestion=str(result["suggestion"]).strip() or "对照评分要点补全缺失步骤。",
                encouragement=self._build_encouragement(is_correct, ratio),
                error_pattern=error_pattern,
                llm_used=True,
            )

        standard_answer = prepared.standard_answer or ""
        is_correct = self._compare_objective_answer(
            prepared.user_answer,
            standard_answer,
            normalized_type,
        )
        ratio = 1.0 if is_correct else 0.0
        comment = "回答正确，继续保持。" if is_correct else "本题回答错误，需要回看解析。"
        suggestion = (
            "继续完成下一题，并留意同知识点迁移应用。"
            if is_correct
            else "先复盘知识点定义和典型例题，再做同知识点专项练习。"
        )
        return EvaluationOutcome(
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            max_score=1.0,
            ratio=ratio,
            comment=comment,
            suggestion=suggestion,
            encouragement=self._build_encouragement(is_correct, ratio),
            error_pattern=self._detect_error_pattern(prepared=prepared, is_correct=is_correct, ratio=ratio),
            llm_used=False,
        )

    def _prepare_submission(self, payload: AnswerRecordSubmission) -> PreparedSubmission:
        with self._session_factory() as session:
            user = self._resolve_user(session, payload.user_id)
            exercise_id_int = self._normalize_external_integer(payload.exercise_id)
            exercise = session.get(Exercise, exercise_id_int)
            exercise_content = self._parse_exercise_content(exercise.content) if exercise is not None else {}
            normalized_type = normalize_exercise_type(
                payload.exercise_type
                or str(exercise_content.get("exercise_type") or exercise.type if exercise is not None else "choice")
            )
            difficulty = normalize_difficulty(
                payload.difficulty
                or str(exercise_content.get("difficulty") or self._map_difficulty_level(exercise))
            )
            knowledge_point_ids = list(payload.knowledge_point_ids)
            if not knowledge_point_ids and exercise_content.get("knowledge_point_ids"):
                knowledge_point_ids = [str(item) for item in exercise_content["knowledge_point_ids"]]
            if not knowledge_point_ids and exercise is not None:
                knowledge_point = session.get(KnowledgePoint, exercise.knowledge_point_id)
                if knowledge_point is not None:
                    knowledge_point_ids = [knowledge_point.name]

            if not knowledge_point_ids:
                raise ValueError("knowledge_point_ids is required when the exercise has no stored metadata.")

            standard_answer = payload.standard_answer or (exercise.answer if exercise is not None else None)
            reference_answer = (
                payload.reference_answer
                or exercise_content.get("reference_answer")
                or (exercise.answer if exercise is not None and normalized_type in {"short_answer", "code"} else None)
            )
            max_score = (
                float(payload.max_score)
                if payload.max_score is not None
                else float(exercise_content.get("max_score", 100.0 if normalized_type in {"short_answer", "code"} else 1.0))
            )
            if normalized_type in {"short_answer", "code"} and not reference_answer:
                raise ValueError("Subjective submissions require reference_answer or stored exercise answer.")
            if normalized_type not in {"short_answer", "code"} and not standard_answer:
                raise ValueError("Objective submissions require standard_answer or stored exercise answer.")

            chapter_id = payload.chapter_id or self._string_or_none(exercise_content.get("chapter_id"))
            chapter_name = payload.chapter_name or self._string_or_none(exercise_content.get("chapter_name"))
            explanation = payload.explanation or (exercise.analysis if exercise is not None else "") or ""
            if not explanation:
                explanation = self._string_or_none(exercise_content.get("analysis")) or ""
            prompt_text = payload.exercise_content or self._string_or_none(exercise_content.get("exercise_content")) or ""
            if not prompt_text and exercise is not None:
                prompt_text = self._string_or_none(exercise_content.get("prompt")) or ""

            return PreparedSubmission(
                user_id_int=user.id,
                user_id_str=str(user.id),
                student_name=payload.student_name or user.username,
                exercise_id_int=exercise_id_int,
                exercise_id_str=str(payload.exercise_id),
                user_answer=payload.user_answer,
                knowledge_point_ids=knowledge_point_ids,
                exercise_type=normalized_type,
                difficulty=difficulty,
                standard_answer=standard_answer,
                reference_answer=reference_answer,
                max_score=max_score,
                exercise_content=prompt_text or explanation,
                explanation=explanation,
                chapter_id=chapter_id,
                chapter_name=chapter_name,
                time_spent=payload.time_spent,
                max_time=self._resolve_max_time(normalized_type, difficulty),
            )

    def _persist_submission(
        self,
        prepared: PreparedSubmission,
        outcome: EvaluationOutcome,
    ) -> tuple[AnswerEvaluationResult, list[tuple[str, dict[str, Any]]]]:
        logger.info(
            "persisting evaluation user_id=%s exercise_id=%s is_correct=%s",
            prepared.user_id_int,
            prepared.exercise_id_str,
            outcome.is_correct,
        )
        with self._session_factory() as session:
            user = session.get(User, prepared.user_id_int)
            if user is None:
                raise ValueError(f"User {prepared.user_id_int} not found.")

            exercise = self._upsert_exercise(session, prepared)
            profile = self._get_or_create_profile(session, prepared.user_id_int)
            answered_at = datetime.now(UTC)
            answer_record = AnswerRecord(
                user_id=prepared.user_id_int,
                exercise_id=exercise.id,
                user_answer=prepared.user_answer,
                is_correct=outcome.is_correct,
                time_spent=int(round(prepared.time_spent)),
                evaluation_json={
                    "exercise_id": prepared.exercise_id_str,
                    "knowledge_point_ids": prepared.knowledge_point_ids,
                    "exercise_type": prepared.exercise_type,
                    "difficulty": prepared.difficulty,
                    "score": outcome.score,
                    "max_score": outcome.max_score,
                    "ratio": outcome.ratio,
                    "comment": outcome.comment,
                    "suggestion": outcome.suggestion,
                    "encouragement": outcome.encouragement,
                    "error_pattern": outcome.error_pattern,
                    "standard_answer": prepared.standard_answer,
                    "reference_answer": prepared.reference_answer,
                    "exercise_content": prepared.exercise_content,
                    "explanation": prepared.explanation,
                    "chapter_id": prepared.chapter_id,
                    "chapter_name": prepared.chapter_name,
                    "llm_used": outcome.llm_used,
                },
                created_at=answered_at,
            )
            session.add(answer_record)
            session.flush()

            updates = self._profile_updater.update_profile(
                profile,
                knowledge_point_ids=prepared.knowledge_point_ids,
                is_correct=outcome.is_correct,
                time_spent=prepared.time_spent,
                max_time=prepared.max_time,
                difficulty=prepared.difficulty,
                exercise_id=prepared.exercise_id_str,
                answer_record_id=answer_record.id,
                score=outcome.score,
                ratio=outcome.ratio,
                error_pattern=outcome.error_pattern,
                chapter_id=prepared.chapter_id,
                answered_at=answered_at,
            )
            self._update_profile_side_channels(profile, updates, prepared, outcome, answered_at)
            session.add(profile)
            session.commit()
            session.refresh(answer_record)

            weak_points = [item.knowledge_point_id for item in updates if item.weak]
            result = AnswerEvaluationResult(
                user_id=prepared.user_id_str,
                exercise_id=prepared.exercise_id_str,
                answer_record_id=answer_record.id,
                is_correct=outcome.is_correct,
                score=round(outcome.score, 4),
                max_score=round(outcome.max_score, 4),
                ratio=round(outcome.ratio, 4),
                comment=outcome.comment,
                suggestion=outcome.suggestion,
                encouragement=outcome.encouragement,
                explanation=prepared.explanation or None,
                error_pattern=outcome.error_pattern,
                weak_knowledge_points=weak_points,
                knowledge_points=[
                    KnowledgePointFeedback(
                        knowledge_point_id=item.knowledge_point_id,
                        mastery_score=round(item.mastery_score, 4),
                        recent_accuracy=round(item.recent_accuracy, 2),
                        consecutive_incorrect=item.consecutive_incorrect,
                        weak=item.weak,
                        error_pattern=item.error_pattern,
                    )
                    for item in updates
                ],
                created_at=answered_at,
            )
            events = self._build_events(prepared, updates, answered_at)
            logger.info(
                "evaluation persisted answer_record_id=%s weak_points=%s",
                answer_record.id,
                weak_points,
            )
            return result, events

    def _load_user_context(self, user_id: int) -> tuple[list[AnswerTrace], UserProfile, str]:
        with self._session_factory() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError(f"User {user_id} not found.")
            profile = self._get_or_create_profile(session, user_id)
            traces = self._get_user_traces(session, user_id)
            return traces, profile, user.username

    def _clear_mistake_notebook(self, user_id: int) -> MistakeNotebookClearResult:
        with self._session_factory() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError(f"User {user_id} not found.")

            profile = self._get_or_create_profile(session, user_id)
            traces = self._get_user_traces(session, user_id)
            visible_mistakes = self._filter_active_mistake_traces(traces, profile)
            cleared_at = datetime.now(UTC)

            habits = dict(profile.habits or {})
            habits["mistake_notebook_cleared_at"] = cleared_at.isoformat()
            profile.habits = habits
            session.add(profile)
            session.commit()

            return MistakeNotebookClearResult(
                user_id=user_id,
                cleared_count=len(visible_mistakes),
                cleared_at=cleared_at,
            )

    def _get_user_traces(self, session: Session, user_id: int) -> list[AnswerTrace]:
        query = (
            session.query(AnswerRecord, Exercise)
            .join(Exercise, Exercise.id == AnswerRecord.exercise_id)
            .filter(AnswerRecord.user_id == user_id)
            .order_by(AnswerRecord.created_at.asc(), AnswerRecord.id.asc())
        )
        traces: list[AnswerTrace] = []
        for answer_record, exercise in query.all():
            metadata = answer_record.evaluation_json if isinstance(answer_record.evaluation_json, dict) else {}
            content = self._parse_exercise_content(exercise.content)
            knowledge_point_ids = metadata.get("knowledge_point_ids") or content.get("knowledge_point_ids") or []
            if not knowledge_point_ids:
                knowledge_point = session.get(KnowledgePoint, exercise.knowledge_point_id)
                if knowledge_point is not None:
                    knowledge_point_ids = [knowledge_point.name]
            question_type = normalize_exercise_type(
                str(metadata.get("exercise_type") or content.get("exercise_type") or exercise.type or "choice")
            )
            difficulty = normalize_difficulty(
                str(metadata.get("difficulty") or content.get("difficulty") or self._map_difficulty_level(exercise))
            )
            score = float(metadata.get("score", 1.0 if answer_record.is_correct else 0.0))
            max_score = float(metadata.get("max_score", 1.0))
            ratio = float(metadata.get("ratio", (score / max_score) if max_score else 0.0))
            traces.append(
                AnswerTrace(
                    answer_record_id=answer_record.id,
                    user_id=user_id,
                    exercise_id=exercise.id,
                    exercise_id_str=str(metadata.get("exercise_id") or exercise.id),
                    knowledge_point_ids=[str(item) for item in knowledge_point_ids],
                    question_type=question_type,
                    difficulty=difficulty,
                    chapter_id=self._string_or_none(metadata.get("chapter_id") or content.get("chapter_id")),
                    chapter_name=self._string_or_none(metadata.get("chapter_name") or content.get("chapter_name")),
                    prompt=str(metadata.get("exercise_content") or content.get("exercise_content") or ""),
                    options=str(metadata.get("options") or content.get("options") or ""),
                    user_answer=answer_record.user_answer,
                    correct_answer=str(metadata.get("standard_answer") or exercise.answer),
                    reference_answer=self._string_or_none(metadata.get("reference_answer") or content.get("reference_answer")),
                    explanation=str(metadata.get("explanation") or exercise.analysis or ""),
                    is_correct=bool(answer_record.is_correct),
                    score=score,
                    max_score=max_score,
                    ratio=ratio,
                    time_spent=float(answer_record.time_spent),
                    error_pattern=str(metadata.get("error_pattern") or "unknown"),
                    suggestion=str(metadata.get("suggestion") or ""),
                    comment=str(metadata.get("comment") or ""),
                    created_at=self._ensure_utc_datetime(answer_record.created_at),
                )
        )
        return traces

    def _filter_active_mistake_traces(
        self,
        traces: list[AnswerTrace],
        profile: UserProfile,
    ) -> list[AnswerTrace]:
        cleared_at = self._get_mistake_notebook_cleared_at(profile)
        return [
            item
            for item in traces
            if not item.is_correct and (cleared_at is None or item.created_at > cleared_at)
        ]

    def _get_mistake_notebook_cleared_at(self, profile: UserProfile) -> datetime | None:
        habits = profile.habits if isinstance(profile.habits, dict) else {}
        raw_value = habits.get("mistake_notebook_cleared_at")
        if not raw_value:
            return None
        if isinstance(raw_value, datetime):
            return self._ensure_utc_datetime(raw_value)
        if isinstance(raw_value, str):
            try:
                return self._ensure_utc_datetime(datetime.fromisoformat(raw_value))
            except ValueError:
                return None
        return None

    def _build_stage_statuses(
        self,
        traces: list[AnswerTrace],
        profile: UserProfile,
    ) -> list[KnowledgePointStageStatus]:
        grouped: dict[str, list[AnswerTrace]] = defaultdict(list)
        for trace in traces:
            for knowledge_point_id in trace.knowledge_point_ids:
                grouped[knowledge_point_id].append(trace)

        mastery_json = profile.mastery_json if isinstance(profile.mastery_json, dict) else {}
        statuses: list[KnowledgePointStageStatus] = []
        for knowledge_point_id, items in grouped.items():
            profile_item = mastery_json.get(knowledge_point_id, {})
            wrong_patterns = Counter(item.error_pattern for item in items if not item.is_correct)
            statuses.append(
                KnowledgePointStageStatus(
                    knowledge_point_id=knowledge_point_id,
                    mastery_score=float(profile_item.get("score", 0)) if isinstance(profile_item, dict) else 0.0,
                    accuracy=self._calculate_accuracy(items),
                    attempts=len(items),
                    weak=bool(profile_item.get("weak")) if isinstance(profile_item, dict) else False,
                    dominant_error_pattern=wrong_patterns.most_common(1)[0][0]
                    if wrong_patterns
                    else "none",
                )
            )
        statuses.sort(key=lambda item: (item.weak is False, item.accuracy, item.mastery_score))
        return statuses

    def _build_evidence(self, traces: list[AnswerTrace]) -> ReportEvidence:
        total_answers = len(traces)
        correct_answers = sum(1 for item in traces if item.is_correct)
        accuracy = round((correct_answers / total_answers) * 100) if total_answers else 0
        average_time_spent = round(sum(item.time_spent for item in traces) / total_answers) if total_answers else 0
        average_score = round(
            sum((item.score / item.max_score) * 100 for item in traces if item.max_score) / total_answers
        ) if total_answers else 0
        mistake_count = sum(1 for item in traces if not item.is_correct)
        by_type: dict[str, list[AnswerTrace]] = defaultdict(list)
        by_kp: dict[str, list[AnswerTrace]] = defaultdict(list)
        for item in traces:
            by_type[item.question_type].append(item)
            for knowledge_point_id in item.knowledge_point_ids:
                by_kp[knowledge_point_id].append(item)

        strongest_types = [
            compatibility_question_type(key)
            for key, value in by_type.items()
            if self._calculate_accuracy(value) >= 80
        ]
        weakest_types = [
            compatibility_question_type(key)
            for key, value in by_type.items()
            if self._calculate_accuracy(value) < 60
        ]
        kp_accuracies = {key: self._calculate_accuracy(value) for key, value in by_kp.items()}
        weakest_knowledge_point = min(kp_accuracies, key=kp_accuracies.get) if kp_accuracies else None
        latest_mistake = next((item for item in reversed(traces) if not item.is_correct), None)
        return ReportEvidence(
            total_answers=total_answers,
            correct_answers=correct_answers,
            accuracy=accuracy,
            average_time_spent=average_time_spent,
            average_score=average_score,
            mistake_count=mistake_count,
            strongest_question_types=strongest_types,
            weakest_question_types=weakest_types,
            weakest_knowledge_point=weakest_knowledge_point,
            weakest_knowledge_accuracy=round(kp_accuracies[weakest_knowledge_point])
            if weakest_knowledge_point is not None
            else None,
            latest_mistake=LatestMistakeEvidence(
                knowledge_point=latest_mistake.knowledge_point_ids[0]
                if latest_mistake and latest_mistake.knowledge_point_ids
                else "unknown",
                question_type=compatibility_question_type(latest_mistake.question_type) if latest_mistake else "unknown",
                user_answer=latest_mistake.user_answer if latest_mistake else "",
                correct_answer=latest_mistake.correct_answer if latest_mistake else "",
                analysis=latest_mistake.explanation if latest_mistake else "",
            )
            if latest_mistake
            else None,
        )

    def _find_most_improved(
        self,
        traces: list[AnswerTrace],
        month_start: datetime,
        middle: datetime,
    ) -> str | None:
        grouped: dict[str, dict[str, list[AnswerTrace]]] = defaultdict(lambda: {"first": [], "second": []})
        for trace in traces:
            bucket = "first" if trace.created_at < middle else "second"
            for knowledge_point_id in trace.knowledge_point_ids:
                grouped[knowledge_point_id][bucket].append(trace)

        best_name: str | None = None
        best_gain = float("-inf")
        for knowledge_point_id, buckets in grouped.items():
            if not buckets["second"]:
                continue
            first_accuracy = self._calculate_accuracy(buckets["first"])
            second_accuracy = self._calculate_accuracy(buckets["second"])
            gain = second_accuracy - first_accuracy
            if gain > best_gain:
                best_gain = gain
                best_name = knowledge_point_id
        return best_name

    def _find_still_weak(self, traces: list[AnswerTrace], profile: UserProfile) -> list[str]:
        grouped: dict[str, list[AnswerTrace]] = defaultdict(list)
        for trace in traces:
            for knowledge_point_id in trace.knowledge_point_ids:
                grouped[knowledge_point_id].append(trace)
        mastery_json = profile.mastery_json if isinstance(profile.mastery_json, dict) else {}
        candidates: list[tuple[bool, float, float, str]] = []
        for knowledge_point_id, items in grouped.items():
            profile_item = mastery_json.get(knowledge_point_id, {})
            weak = bool(profile_item.get("weak")) if isinstance(profile_item, dict) else False
            mastery = float(profile_item.get("score", 0)) if isinstance(profile_item, dict) else 0.0
            accuracy = self._calculate_accuracy(items)
            candidates.append((not weak, accuracy, mastery, knowledge_point_id))
        candidates.sort()
        return [item[3] for item in candidates[:3]]

    def _update_profile_side_channels(
        self,
        profile: UserProfile,
        updates: list[Any],
        prepared: PreparedSubmission,
        outcome: EvaluationOutcome,
        answered_at: datetime,
    ) -> None:
        habits = dict(profile.habits or {})
        cognitive = dict(profile.cognitive_abilities or {})
        total_answers = int(habits.get("total_answers", 0)) + 1
        prev_avg = float(habits.get("average_time_spent", 0.0))
        new_avg = prepared.time_spent if total_answers == 1 else ((prev_avg * (total_answers - 1)) + prepared.time_spent) / total_answers
        habits.update(
            {
                "total_answers": total_answers,
                "average_time_spent": round(new_avg, 4),
                "last_answered_at": answered_at.isoformat(),
            }
        )
        weak_points = [item.knowledge_point_id for item in updates if item.weak]
        cognitive.update(
            {
                "last_error_pattern": outcome.error_pattern,
                "weak_knowledge_points": weak_points,
                "last_feedback": outcome.comment,
            }
        )
        profile.habits = habits
        profile.cognitive_abilities = cognitive

    def _build_events(
        self,
        prepared: PreparedSubmission,
        updates: list[Any],
        answered_at: datetime,
    ) -> list[tuple[str, dict[str, Any]]]:
        events: list[tuple[str, dict[str, Any]]] = []
        for update in updates:
            profile_event = {
                "event_type": "ProfileUpdateEvent",
                "user_id": prepared.user_id_str,
                "knowledge_point_id": update.knowledge_point_id,
                "new_mastery": round(update.mastery_score, 4),
                "weak": update.weak,
                "recent_accuracy": round(update.recent_accuracy, 2),
                "consecutive_incorrect": update.consecutive_incorrect,
                "error_pattern": update.error_pattern,
                "updated_at": answered_at.isoformat(),
            }
            events.append((PROFILE_UPDATE_QUEUE, profile_event))
            if update.weak:
                events.append(
                    (
                        PATH_ADJUSTMENT_QUEUE,
                        {
                            "event_type": "PathAdjustmentRequest",
                            "user_id": prepared.user_id_str,
                            "knowledge_point_id": update.knowledge_point_id,
                            "reason": "weak_knowledge_point_detected",
                            "priority": "high",
                            "requested_at": answered_at.isoformat(),
                        },
                    )
                )
        return events

    async def _publish_events(self, events: list[tuple[str, dict[str, Any]]]) -> None:
        for queue_name, message in events:
            await asyncio.to_thread(self._publisher.publish, queue_name, message)

    def _upsert_exercise(self, session: Session, prepared: PreparedSubmission) -> Exercise:
        primary_knowledge_point = self._get_or_create_knowledge_point(session, prepared.knowledge_point_ids[0])
        exercise = session.get(Exercise, prepared.exercise_id_int)
        content_payload = {
            "external_exercise_id": prepared.exercise_id_str,
            "exercise_content": prepared.exercise_content,
            "knowledge_point_ids": prepared.knowledge_point_ids,
            "exercise_type": prepared.exercise_type,
            "difficulty": prepared.difficulty,
            "standard_answer": prepared.standard_answer,
            "reference_answer": prepared.reference_answer,
            "max_score": prepared.max_score,
            "chapter_id": prepared.chapter_id,
            "chapter_name": prepared.chapter_name,
            "analysis": prepared.explanation,
        }
        answer = prepared.standard_answer or prepared.reference_answer or ""
        if exercise is None:
            exercise = Exercise(
                id=prepared.exercise_id_int,
                knowledge_point_id=primary_knowledge_point.id,
                type=prepared.exercise_type,
                difficulty=self._difficulty_to_level(prepared.difficulty),
                content=json.dumps(content_payload, ensure_ascii=False),
                answer=answer,
                analysis=prepared.explanation,
            )
            session.add(exercise)
            session.flush()
            return exercise

        exercise.knowledge_point_id = primary_knowledge_point.id
        exercise.type = prepared.exercise_type
        exercise.difficulty = self._difficulty_to_level(prepared.difficulty)
        exercise.content = json.dumps(content_payload, ensure_ascii=False)
        exercise.answer = answer
        exercise.analysis = prepared.explanation
        session.add(exercise)
        session.flush()
        return exercise

    def _get_or_create_profile(self, session: Session, user_id: int) -> UserProfile:
        profile = session.get(UserProfile, user_id)
        if profile is not None:
            return profile
        profile = UserProfile(
            user_id=user_id,
            mastery_json={},
            learning_style="",
            cognitive_abilities={},
            habits={},
        )
        session.add(profile)
        session.flush()
        return profile

    def _get_or_create_knowledge_point(self, session: Session, knowledge_point_id: str) -> KnowledgePoint:
        knowledge_point = session.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point_id).first()
        if knowledge_point is not None:
            return knowledge_point
        knowledge_point = KnowledgePoint(
            name=knowledge_point_id,
            description=f"Evaluation-tracked knowledge point {knowledge_point_id}",
            difficulty=2,
            importance=3,
            subject_id=1,
        )
        session.add(knowledge_point)
        session.flush()
        return knowledge_point

    def _resolve_user(self, session: Session, user_id: str) -> User:
        if user_id.isdigit():
            user = session.get(User, int(user_id))
            if user is not None:
                return user
        user = session.query(User).filter(User.username == user_id).first()
        if user is None:
            raise ValueError(f"User '{user_id}' not found.")
        return user

    def _normalize_user_id(self, user_id: str) -> int:
        with self._session_factory() as session:
            return self._resolve_user(session, user_id).id

    def _save_report(self, user_id: int, report_type: str, content_json: dict[str, Any]) -> None:
        with self._session_factory() as session:
            session.add(LearningReport(user_id=user_id, report_type=report_type, content_json=content_json))
            session.commit()

    def _empty_detail(self, user_id: int, report_type: str, title: str) -> ReportDetail:
        return ReportDetail(
            report_type=report_type,
            user_id=user_id,
            title=title,
            summary="暂无真实答题记录，系统无法生成分析报告。",
            strengths=[],
            weaknesses=["请先提交真实答题数据。"],
            next_actions=["完成至少一组真实练习后再查看报告。"],
            evidence=ReportEvidence(),
        )

    def _latest_chapter_id(self, traces: list[AnswerTrace]) -> str | None:
        for item in reversed(traces):
            if item.chapter_id:
                return item.chapter_id
        return None

    def _select_latest_stage_traces(
        self,
        traces: list[AnswerTrace],
        chapter_id: str | None,
    ) -> list[AnswerTrace]:
        """Select a stage slice from real traces, even for legacy records without chapter metadata."""

        if chapter_id is not None:
            chapter_traces = [item for item in traces if item.chapter_id == chapter_id]
            if chapter_traces:
                return chapter_traces

        if not traces:
            return []

        latest_knowledge_point = next(
            (item.knowledge_point_ids[0] for item in reversed(traces) if item.knowledge_point_ids),
            None,
        )
        if latest_knowledge_point is None:
            return traces[-5:]

        knowledge_traces = [item for item in traces if latest_knowledge_point in item.knowledge_point_ids]
        return knowledge_traces or traces[-5:]

    def _calculate_accuracy(self, traces: list[AnswerTrace]) -> float:
        if not traces:
            return 0.0
        return round((sum(1 for item in traces if item.is_correct) / len(traces)) * 100, 2)

    def _compare_objective_answer(self, user_answer: str, standard_answer: str, question_type: str) -> bool:
        normalized_user = self._normalize_answer_text(user_answer)
        normalized_standard = self._normalize_answer_text(standard_answer)
        if question_type == "judge":
            return self._normalize_judge_answer(normalized_user) == self._normalize_judge_answer(normalized_standard)
        return normalized_user == normalized_standard

    def _normalize_answer_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().casefold())

    def _normalize_judge_answer(self, value: str) -> str:
        mapping = {
            "true": "true",
            "t": "true",
            "对": "true",
            "正确": "true",
            "yes": "true",
            "1": "true",
            "false": "false",
            "f": "false",
            "错": "false",
            "错误": "false",
            "no": "false",
            "0": "false",
        }
        return mapping.get(value, value)

    def _detect_error_pattern(
        self,
        *,
        prepared: PreparedSubmission,
        is_correct: bool,
        ratio: float,
    ) -> str:
        if is_correct:
            return "none"
        if not prepared.user_answer.strip():
            return "missing_answer"
        if prepared.exercise_type == "code":
            return "coding_logic_error"
        if prepared.exercise_type in {"short_answer", "code"} and ratio > 0:
            return "incomplete_reasoning"
        if self._looks_numeric(prepared.user_answer) and self._looks_numeric(prepared.standard_answer or ""):
            return "calculation_error"
        if prepared.time_spent <= max(8.0, prepared.max_time * 0.15):
            return "concept_confusion"
        return "reasoning_gap"

    def _build_encouragement(self, is_correct: bool, ratio: float) -> str:
        if is_correct and ratio >= 1.0:
            return "这题处理得很稳，继续保持。"
        if is_correct:
            return "方向是对的，再把细节打磨一下会更好。"
        return "这次没答对也没关系，复盘后再做一题会进步更快。"

    def _looks_numeric(self, value: str) -> bool:
        cleaned = value.replace(".", "", 1).replace("-", "", 1)
        return bool(cleaned) and cleaned.isdigit()

    def _resolve_max_time(self, exercise_type: str, difficulty: str) -> float:
        return MAX_TIME_RULES[exercise_type][difficulty]

    def _difficulty_to_level(self, difficulty: str) -> int:
        return {"basic": 1, "intermediate": 2, "advanced": 3}[difficulty]

    def _map_difficulty_level(self, exercise: Exercise | None) -> str:
        if exercise is None:
            return "intermediate"
        if exercise.difficulty <= 1:
            return "basic"
        if exercise.difficulty == 2:
            return "intermediate"
        return "advanced"

    def _parse_exercise_content(self, content: str | None) -> dict[str, Any]:
        if not content:
            return {}
        try:
            payload = json.loads(content)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _normalize_external_integer(self, value: str) -> int:
        if value.isdigit():
            return int(value)
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return int(digest[:12], 16) % 2_000_000_000

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _ensure_utc_datetime(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.fromtimestamp(0, UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
