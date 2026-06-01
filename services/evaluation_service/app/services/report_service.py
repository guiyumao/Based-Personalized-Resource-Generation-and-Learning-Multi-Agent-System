"""Database-backed evaluation and reporting service."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from common.db.session import SessionLocal
from common.models.learning import (
    AnswerRecord,
    Exercise,
    KnowledgePoint,
    LearningReport,
    UserProfile,
)
from services.evaluation_service.app.schemas.report import (
    AnalyticsSuggestion,
    AnswerRecordIn,
    LatestMistakeEvidence,
    MistakeItem,
    MistakeNotebook,
    PracticeFeedback,
    PracticeSubmission,
    QAMistakeSubmission,
    RemedialExerciseItem,
    RemedialExerciseSet,
    ReportDetail,
    ReportEvidence,
    ReportSummary,
)
from services.evaluation_service.app.services.profile_updater import LearnerProfileUpdater


QUESTION_TYPE_LABELS = {
    "choice": "选择题",
    "blank": "填空题",
    "judge": "判断题",
    "short_answer": "简答题",
    "programming": "编程题",
}


@dataclass
class PracticeTrace:
    """One persisted practice record normalized for reporting."""

    user_id: int
    exercise_id: int
    knowledge_point: str
    question_type: str
    user_answer: str
    correct_answer: str
    analysis: str
    is_correct: bool
    time_spent: int
    score: int
    difficulty: str


class ReportService:
    """Report generator backed by the real project database."""

    def __init__(self, db: Session | None = None) -> None:
        self._owns_db = db is None
        self.db = db or SessionLocal()
        self.profile_updater = LearnerProfileUpdater(self.db)

    def __del__(self) -> None:
        if getattr(self, "_owns_db", False):
            try:
                self.db.close()
            except Exception:
                pass

    def submit_answer(self, payload: AnswerRecordIn) -> AnswerRecordIn:
        """Store one answer record without additional evaluation."""

        answer = AnswerRecord(
            user_id=payload.user_id,
            exercise_id=payload.exercise_id,
            user_answer=payload.answer,
            is_correct=payload.is_correct,
            time_spent=payload.time_spent,
        )
        self.db.add(answer)
        self.db.commit()
        return payload

    def evaluate_practice(self, payload: PracticeSubmission) -> PracticeFeedback:
        """Evaluate one practice submission, persist it, and update learner mastery."""

        exercise = self._resolve_or_create_exercise(payload)
        is_correct, score = self._score_submission(payload)

        answer = AnswerRecord(
            user_id=payload.user_id,
            exercise_id=exercise.id,
            user_answer=payload.user_answer,
            is_correct=is_correct,
            time_spent=payload.time_spent,
        )
        self.db.add(answer)
        self.db.flush()

        updated_profile = self.profile_updater.update_after_practice(
            user_id=payload.user_id,
            knowledge_point=payload.knowledge_point,
            is_correct=is_correct,
            time_spent=payload.time_spent,
            question_type=payload.question_type,
        )
        self.db.commit()

        if is_correct:
            feedback = "回答正确，这道题的核心思路已经掌握，可以继续推进下一题。"
            suggested_action = "保持当前节奏，继续下一题。"
        else:
            feedback = "这道题没有答对，建议先完整看解析，再用自己的话复述一遍解题步骤。"
            suggested_action = "不要重复提交原题，先进入错题复盘，再做同知识点变式题。"

        mastery_after_update = self._get_mastery_score(updated_profile, payload.knowledge_point)
        return PracticeFeedback(
            user_id=payload.user_id,
            exercise_id=exercise.id,
            is_correct=is_correct,
            score=score,
            feedback=feedback,
            suggested_action=suggested_action,
            analysis=payload.analysis,
            mastery_after_update=mastery_after_update,
        )

    def record_qa_mistake(self, payload: QAMistakeSubmission) -> MistakeItem:
        """Persist one QA-derived mistake so reports and notebooks can reuse it."""

        exercise = self._resolve_or_create_qa_exercise(payload)
        answer = (
            self.db.query(AnswerRecord)
            .filter(
                AnswerRecord.user_id == payload.user_id,
                AnswerRecord.exercise_id == exercise.id,
            )
            .order_by(AnswerRecord.id.asc())
            .first()
        )

        if answer is None:
            answer = AnswerRecord(
                user_id=payload.user_id,
                exercise_id=exercise.id,
                user_answer=payload.wrong_answer,
                is_correct=False,
                time_spent=payload.time_spent,
            )
            self.db.add(answer)
        else:
            answer.user_answer = payload.wrong_answer
            answer.is_correct = False
            answer.time_spent = payload.time_spent

        updated_profile = self.profile_updater.update_after_practice(
            user_id=payload.user_id,
            knowledge_point=payload.knowledge_point,
            is_correct=False,
            time_spent=payload.time_spent,
            question_type=payload.question_type,
        )
        self.db.commit()

        return MistakeItem(
            user_id=payload.user_id,
            exercise_id=exercise.id,
            knowledge_point=payload.knowledge_point,
            question_type=payload.question_type,
            user_answer=payload.wrong_answer,
            correct_answer=payload.correct_answer,
            analysis=payload.analysis,
            suggested_action=payload.suggested_action,
        )

    def generate_stage_report(self, user_id: int) -> ReportSummary:
        """Create a stage report summary for a user."""

        evidence = self._build_evidence(self._get_user_traces(user_id))
        summary = (
            f"当前阶段共完成 {evidence.total_answers} 次作答，"
            f"答对 {evidence.correct_answers} 次，整体正确率约为 {evidence.accuracy}%。"
        )
        self._save_report(user_id, "stage", {"summary": summary, "evidence": evidence.model_dump()})
        return ReportSummary(
            report_type="stage",
            user_id=user_id,
            title="阶段学习报告",
            summary=summary,
        )

    def generate_stage_report_detail(self, user_id: int) -> ReportDetail:
        """Create a detailed stage report for the student workspace."""

        traces = self._get_user_traces(user_id)
        evidence = self._build_evidence(traces)
        if not traces:
            return ReportDetail(
                report_type="stage",
                user_id=user_id,
                title="阶段学习报告",
                summary="当前还没有作答记录。先完成一轮练习，系统才会生成更具体的阶段反馈。",
                strengths=["开始练习后，这里会显示你当前阶段已经稳定掌握的能力。"],
                weaknesses=["开始练习后，这里会指出你当前最需要补强的题型和知识点。"],
                next_actions=["先完成一组练习题，再回到这里查看阶段反馈。"],
                evidence=evidence,
            )

        strengths = [
            f"本阶段共作答 {evidence.total_answers} 次，答对 {evidence.correct_answers} 次，整体正确率为 {evidence.accuracy}%。",
            f"平均每题耗时约 {evidence.average_time_spent} 秒，已经形成了可追踪的作答节奏。",
        ]
        if evidence.strongest_question_types:
            strengths.append(f"当前表现相对稳定的题型：{'、'.join(evidence.strongest_question_types[:3])}。")

        weaknesses: list[str] = []
        if evidence.weakest_knowledge_point and evidence.weakest_knowledge_accuracy is not None:
            weaknesses.append(
                f"当前最薄弱的知识点是 {evidence.weakest_knowledge_point}，正确率为 {evidence.weakest_knowledge_accuracy}%。"
            )
        if evidence.weakest_question_types:
            weaknesses.append(f"当前失分更集中的题型：{'、'.join(evidence.weakest_question_types[:3])}。")
        if evidence.latest_mistake is not None:
            weaknesses.append(
                f"最近一次错题出现在 {evidence.latest_mistake.knowledge_point} / "
                f"{self._label_question_type(evidence.latest_mistake.question_type)}，"
                f"暴露的问题是：{evidence.latest_mistake.analysis}"
            )

        next_actions = []
        if evidence.weakest_knowledge_point:
            next_actions.append(f"优先复练 {evidence.weakest_knowledge_point} 相关题目，先同类再变式。")
        if evidence.weakest_question_types:
            next_actions.append(f"下一轮练习重点补强 {'、'.join(evidence.weakest_question_types[:2])}。")
        next_actions.append("每道错题都先看标准答案与解析，再用自己的话复述一遍解题步骤。")

        report = ReportDetail(
            report_type="stage",
            user_id=user_id,
            title="阶段学习报告",
            summary=(
                f"当前共完成 {evidence.total_answers} 次作答，阶段正确率约为 {evidence.accuracy}%，"
                f"平均每题耗时 {evidence.average_time_spent} 秒。"
            ),
            strengths=strengths,
            weaknesses=weaknesses,
            next_actions=next_actions,
            evidence=evidence,
        )
        self._save_report(user_id, "stage", report.model_dump())
        return report

    def generate_comprehensive_report(self, user_id: int) -> ReportSummary:
        """Create a comprehensive report summary for a user."""

        evidence = self._build_evidence(self._get_user_traces(user_id))
        summary = (
            f"累计作答 {evidence.total_answers} 次，综合正确率约为 {evidence.accuracy}%，"
            f"累计错题 {evidence.mistake_count} 道。"
        )
        self._save_report(user_id, "comprehensive", {"summary": summary, "evidence": evidence.model_dump()})
        return ReportSummary(
            report_type="comprehensive",
            user_id=user_id,
            title="综合学习报告",
            summary=summary,
        )

    def generate_comprehensive_report_detail(self, user_id: int) -> ReportDetail:
        """Create a detailed comprehensive report."""

        traces = self._get_user_traces(user_id)
        evidence = self._build_evidence(traces)
        if not traces:
            return ReportDetail(
                report_type="comprehensive",
                user_id=user_id,
                title="综合学习报告",
                summary="当前还没有足够的作答记录。先完成练习，系统才会生成综合趋势反馈。",
                strengths=["开始积累练习记录后，这里会显示你的长期优势。"],
                weaknesses=["开始积累练习记录后，这里会显示重复出现的薄弱点。"],
                next_actions=["先完成基础练习，再回来查看综合报告。"],
                evidence=evidence,
            )

        strengths = [
            f"累计完成 {evidence.total_answers} 次作答，综合正确率 {evidence.accuracy}%，平均得分 {evidence.average_score} 分。",
        ]
        if evidence.strongest_question_types:
            strengths.append(f"当前表现最稳定的题型是 {'、'.join(evidence.strongest_question_types[:2])}。")
        if evidence.accuracy >= 70:
            strengths.append("整体表现已经进入较稳定区间，可以逐步增加进阶题比例。")
        else:
            strengths.append("虽然整体正确率还在爬升，但已经积累了足够的真实数据，可以开始精准补强。")

        weaknesses = [
            f"当前累计错题 {evidence.mistake_count} 道，平均每题耗时约 {evidence.average_time_spent} 秒。",
        ]
        if evidence.weakest_knowledge_point and evidence.weakest_knowledge_accuracy is not None:
            weaknesses.append(
                f"综合来看，最需要补强的知识点是 {evidence.weakest_knowledge_point}，正确率为 {evidence.weakest_knowledge_accuracy}%。"
            )
        if evidence.weakest_question_types:
            weaknesses.append(
                f"当前更容易失分或耗时偏高的题型是 {'、'.join(evidence.weakest_question_types[:3])}。"
            )

        next_actions = []
        if evidence.weakest_knowledge_point:
            next_actions.append(f"接下来优先围绕 {evidence.weakest_knowledge_point} 完成 1 组专项训练。")
        if evidence.weakest_question_types:
            next_actions.append(f"针对 {'、'.join(evidence.weakest_question_types[:2])} 做限时训练，提升结构化作答能力。")
        next_actions.append("保持“作答 -> 看标准答案 -> 复述解析 -> 做变式题”的固定复盘流程。")

        report = ReportDetail(
            report_type="comprehensive",
            user_id=user_id,
            title="综合学习报告",
            summary=(
                f"累计完成 {evidence.total_answers} 次作答，综合正确率 {evidence.accuracy}%，"
                f"平均得分 {evidence.average_score} 分。"
            ),
            strengths=strengths,
            weaknesses=weaknesses,
            next_actions=next_actions,
            evidence=evidence,
        )
        self._save_report(user_id, "comprehensive", report.model_dump())
        return report

    def get_mistake_statistics(self, user_id: int) -> dict[str, object]:
        """Return mistake statistics for a user."""

        notebook = self.get_mistake_notebook(user_id)
        return {
            "user_id": user_id,
            "mistake_count": notebook.mistake_count,
            "exercise_ids": [item.exercise_id for item in notebook.items],
        }

    def get_mistake_notebook(self, user_id: int) -> MistakeNotebook:
        """Return the learner mistake notebook."""

        traces = [item for item in self._get_user_traces(user_id) if not item.is_correct]
        items = [
            MistakeItem(
                user_id=item.user_id,
                exercise_id=item.exercise_id,
                knowledge_point=item.knowledge_point,
                question_type=item.question_type,
                user_answer=item.user_answer,
                correct_answer=item.correct_answer,
                analysis=item.analysis,
                suggested_action="先读懂解析，再做同知识点变式题，不要重复提交原题。",
            )
            for item in traces
        ]
        return MistakeNotebook(user_id=user_id, mistake_count=len(items), items=items)

    def generate_remedial_exercises(self, user_id: int) -> RemedialExerciseSet:
        """Generate variant exercises based on the user's real mistakes."""

        notebook = self.get_mistake_notebook(user_id)
        exercises: list[RemedialExerciseItem] = []
        for index, item in enumerate(notebook.items, start=1):
            prompt = (
                f"变式题 {index}：围绕 {item.knowledge_point} 重新完成一道 {self._label_question_type(item.question_type)}。"
                f"这次重点避免上次暴露的问题：{item.analysis}"
            )
            options = (
                [
                    "A. 先确认题目考查对象",
                    "B. 逐步拆解条件与步骤",
                    "C. 检查边界、循环或判断条件",
                    "D. 对照样例验证结果",
                ]
                if item.question_type == "choice"
                else []
            )
            exercises.append(
                RemedialExerciseItem(
                    exercise_id=9000 + index,
                    knowledge_point=item.knowledge_point,
                    question_type=item.question_type,
                    prompt=prompt,
                    options=options,
                    answer=item.correct_answer,
                    analysis=f"这是一道根据真实错题生成的变式练习，目标是巩固 {item.knowledge_point} 并修正同类错误。",
                    source_exercise_id=item.exercise_id,
                )
            )

        return RemedialExerciseSet(
            user_id=user_id,
            generated_from_mistakes=len(exercises),
            summary="已根据真实错题记录自动生成变式重练题目。",
            exercises=exercises,
        )

    def generate_profile_snapshot(self, user_id: int) -> dict[str, object]:
        """Generate a learner dashboard snapshot from persisted answer behavior."""

        traces = self._get_user_traces(user_id)
        profile = self.db.get(UserProfile, user_id)
        total_count = len(traces)
        correct_count = sum(1 for item in traces if item.is_correct)
        average_time = round(sum(item.time_spent for item in traces) / total_count) if total_count else 0
        accuracy = round((correct_count / total_count) * 100) if total_count else 62
        mistake_count = len([item for item in traces if not item.is_correct])
        mastery_json = profile.mastery_json if profile and isinstance(profile.mastery_json, dict) else {}

        logical_score = min(95, max(45, accuracy))
        stability_score = min(92, max(40, 88 - mistake_count * 6))
        speed_score = min(90, max(35, 85 - max(0, average_time - 20)))
        reflection_score = min(96, max(42, 78 - mistake_count * 3 + correct_count * 2))

        heatmap = self._build_profile_heatmap(mastery_json, accuracy)
        return {
            "user_id": user_id,
            "learning_style": profile.learning_style if profile and profile.learning_style else "visual + practice",
            "mastery_overview": accuracy,
            "weekly_focus_minutes": max(45, total_count * 18),
            "habit_summary": self._build_habit_summary(profile),
            "radar_metrics": [
                {"dimension": "知识掌握", "score": accuracy},
                {"dimension": "逻辑分析", "score": logical_score},
                {"dimension": "作答稳定性", "score": stability_score},
                {"dimension": "完成速度", "score": speed_score},
                {"dimension": "复盘反思", "score": reflection_score},
            ],
            "heatmap": heatmap,
        }

    def generate_learning_suggestions(self, user_id: int) -> AnalyticsSuggestion:
        """Return concise personalized suggestions from accumulated evidence."""

        traces = self._get_user_traces(user_id)
        evidence = self._build_evidence(traces)
        profile = self.db.get(UserProfile, user_id)

        focus_areas: list[str] = []
        suggestions: list[str] = []

        if evidence.weakest_knowledge_point:
            focus_areas.append(evidence.weakest_knowledge_point)
            suggestions.append(f"优先围绕 {evidence.weakest_knowledge_point} 做一轮定向复练。")

        focus_areas.extend(item for item in evidence.weakest_question_types[:2] if item not in focus_areas)
        if evidence.weakest_question_types:
            suggestions.append(f"把 {'、'.join(evidence.weakest_question_types[:2])} 作为下一轮练习重点题型。")

        if evidence.average_time_spent >= 45:
            suggestions.append("最近单题耗时偏长，先做基础题巩固步骤感，再逐步提速。")
        elif evidence.total_answers:
            suggestions.append("保持当前答题节奏，同时增加少量变式题巩固迁移能力。")

        if evidence.accuracy >= 80:
            suggestions.append("整体正确率已较稳定，可以增加进阶题和综合应用题比例。")
        elif evidence.total_answers:
            suggestions.append("先把错题复盘流程固定下来，优先减少重复性错误。")
        else:
            suggestions.append("先完成一组真实练习，系统才能生成更准确的个性化建议。")

        if profile is not None and isinstance(profile.habits, dict):
            study_hours = profile.habits.get("study_hours", {})
            if isinstance(study_hours, dict) and study_hours:
                top_hour = max(study_hours.items(), key=lambda item: int(item[1]))[0]
                suggestions.append(f"尽量把高强度练习安排在你更活跃的 {top_hour} 点附近。")

        recommended_action = (
            f"下一步先复练 {focus_areas[0]}，再回到学习路径继续推进。"
            if focus_areas
            else "下一步先完成一轮练习，积累足够数据后再做精准调优。"
        )

        return AnalyticsSuggestion(
            user_id=user_id,
            suggestions=suggestions[:4],
            focus_areas=focus_areas[:3],
            recommended_action=recommended_action,
        )

    def _resolve_or_create_exercise(self, payload: PracticeSubmission) -> Exercise:
        exercise = self.db.get(Exercise, payload.exercise_id)
        if exercise is not None:
            exercise.answer = payload.correct_answer
            exercise.analysis = payload.analysis
            return exercise

        knowledge_point = self._resolve_or_create_knowledge_point(payload.knowledge_point)
        exercise = Exercise(
            id=payload.exercise_id,
            knowledge_point_id=knowledge_point.id,
            type=payload.question_type,
            difficulty=self._infer_difficulty_level(payload.question_type),
            content=json.dumps(
                {
                    "knowledge_point": payload.knowledge_point,
                    "question_type": payload.question_type,
                    "prompt": "",
                },
                ensure_ascii=False,
            ),
            answer=payload.correct_answer,
            analysis=payload.analysis,
        )
        self.db.add(exercise)
        self.db.flush()
        return exercise

    def _resolve_or_create_qa_exercise(self, payload: QAMistakeSubmission) -> Exercise:
        exercise = self.db.get(Exercise, payload.exercise_id)
        content = json.dumps(
            {
                "knowledge_point": payload.knowledge_point,
                "question_type": payload.question_type,
                "prompt": payload.question_summary,
                "source": "qa",
            },
            ensure_ascii=False,
        )
        if exercise is not None:
            exercise.type = payload.question_type
            exercise.difficulty = self._infer_difficulty_level(payload.question_type)
            exercise.content = content
            exercise.answer = payload.correct_answer
            exercise.analysis = payload.analysis
            return exercise

        knowledge_point = self._resolve_or_create_knowledge_point(payload.knowledge_point)
        exercise = Exercise(
            id=payload.exercise_id,
            knowledge_point_id=knowledge_point.id,
            type=payload.question_type,
            difficulty=self._infer_difficulty_level(payload.question_type),
            content=content,
            answer=payload.correct_answer,
            analysis=payload.analysis,
        )
        self.db.add(exercise)
        self.db.flush()
        return exercise

    def _resolve_or_create_knowledge_point(self, knowledge_point: str) -> KnowledgePoint:
        existing = self.db.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point).first()
        if existing is not None:
            return existing

        record = KnowledgePoint(
            name=knowledge_point,
            description=f"{knowledge_point} 自动建档知识点。",
            difficulty=2,
            importance=3,
            subject_id=1,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def _score_submission(self, payload: PracticeSubmission) -> tuple[bool, int]:
        normalized_user_answer = payload.user_answer.strip().lower()
        normalized_correct_answer = payload.correct_answer.strip().lower()
        is_correct = (
            normalized_correct_answer == normalized_user_answer
            or normalized_correct_answer in normalized_user_answer
            or normalized_user_answer in normalized_correct_answer
        )
        score = (
            100
            if is_correct
            else 60
            if payload.question_type in {"short_answer", "programming"} and normalized_user_answer
            else 0
        )
        return is_correct, score

    def _build_evidence(self, traces: list[PracticeTrace]) -> ReportEvidence:
        total_answers = len(traces)
        correct_answers = sum(1 for item in traces if item.is_correct)
        average_time_spent = round(sum(item.time_spent for item in traces) / total_answers) if total_answers else 0
        average_score = round(sum(item.score for item in traces) / total_answers) if total_answers else 0
        accuracy = round((correct_answers / total_answers) * 100) if total_answers else 0
        type_stats = self._build_question_type_stats(traces)
        strong_types = [name for name, stats in type_stats.items() if stats["accuracy"] >= 80]
        weak_types = [name for name, stats in type_stats.items() if stats["accuracy"] < 60]
        knowledge_point_stats = self._build_knowledge_point_stats(traces)
        weakest_knowledge_point = self._pick_weakest_item(knowledge_point_stats)
        weakest_knowledge_accuracy = (
            knowledge_point_stats[weakest_knowledge_point]["accuracy"]
            if weakest_knowledge_point is not None
            else None
        )
        latest_mistake = next((item for item in reversed(traces) if not item.is_correct), None)

        return ReportEvidence(
            total_answers=total_answers,
            correct_answers=correct_answers,
            accuracy=accuracy,
            average_time_spent=average_time_spent,
            average_score=average_score,
            mistake_count=len([item for item in traces if not item.is_correct]),
            strongest_question_types=[self._label_question_type(name) for name in strong_types],
            weakest_question_types=[self._label_question_type(name) for name in weak_types],
            weakest_knowledge_point=weakest_knowledge_point,
            weakest_knowledge_accuracy=weakest_knowledge_accuracy,
            latest_mistake=LatestMistakeEvidence(
                knowledge_point=latest_mistake.knowledge_point,
                question_type=latest_mistake.question_type,
                user_answer=latest_mistake.user_answer,
                correct_answer=latest_mistake.correct_answer,
                analysis=latest_mistake.analysis,
            )
            if latest_mistake
            else None,
        )

    def _get_user_traces(self, user_id: int) -> list[PracticeTrace]:
        query = (
            self.db.query(AnswerRecord, Exercise)
            .join(Exercise, Exercise.id == AnswerRecord.exercise_id)
            .filter(AnswerRecord.user_id == user_id)
            .order_by(AnswerRecord.id.asc())
        )
        traces: list[PracticeTrace] = []
        for answer_record, exercise in query.all():
            payload = self._parse_exercise_content(exercise.content)
            traces.append(
                PracticeTrace(
                    user_id=user_id,
                    exercise_id=exercise.id,
                    knowledge_point=str(payload.get("knowledge_point") or "未标注知识点"),
                    question_type=str(payload.get("question_type") or exercise.type),
                    user_answer=answer_record.user_answer,
                    correct_answer=exercise.answer,
                    analysis=exercise.analysis,
                    is_correct=bool(answer_record.is_correct),
                    time_spent=answer_record.time_spent,
                    score=self._estimate_score(answer_record, exercise),
                    difficulty=self._map_difficulty(exercise.difficulty),
                )
            )
        return traces

    def _estimate_score(self, answer_record: AnswerRecord, exercise: Exercise) -> int:
        if answer_record.is_correct:
            return 100
        if answer_record.user_answer.strip() and exercise.type in {"short_answer", "programming"}:
            return 60
        return 0

    def _build_question_type_stats(self, traces: list[PracticeTrace]) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0, "accuracy": 0})
        for item in traces:
            stats[item.question_type]["total"] += 1
            stats[item.question_type]["correct"] += int(item.is_correct)
        for item in stats.values():
            item["accuracy"] = round((item["correct"] / item["total"]) * 100) if item["total"] else 0
        return stats

    def _build_knowledge_point_stats(self, traces: list[PracticeTrace]) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0, "accuracy": 0})
        for item in traces:
            stats[item.knowledge_point]["total"] += 1
            stats[item.knowledge_point]["correct"] += int(item.is_correct)
        for item in stats.values():
            item["accuracy"] = round((item["correct"] / item["total"]) * 100) if item["total"] else 0
        return stats

    def _pick_weakest_item(self, stats: dict[str, dict[str, int]]) -> str | None:
        if not stats:
            return None
        return min(stats.items(), key=lambda item: (item[1]["accuracy"], -item[1]["total"]))[0]

    def _build_profile_heatmap(self, mastery_json: dict[str, Any], fallback_accuracy: int) -> list[dict[str, object]]:
        if not mastery_json:
            return [
                {"knowledge_point": "Python 循环", "mastery": fallback_accuracy},
                {"knowledge_point": "条件判断", "mastery": max(35, fallback_accuracy - 8)},
            ]

        cells: list[dict[str, object]] = []
        for key, value in mastery_json.items():
            score = value.get("score", fallback_accuracy) if isinstance(value, dict) else value
            try:
                mastery = max(0, min(100, int(score)))
            except Exception:
                mastery = fallback_accuracy
            cells.append({"knowledge_point": str(key), "mastery": mastery})
        return cells[:12]

    def _build_habit_summary(self, profile: UserProfile | None) -> str:
        if profile is None or not isinstance(profile.habits, dict):
            return "最近学习节奏数据较少，建议继续积累真实作答记录。"

        study_hours = profile.habits.get("study_hours", {})
        if isinstance(study_hours, dict) and study_hours:
            top_hour = max(study_hours.items(), key=lambda item: int(item[1]))[0]
            return f"最近主要集中在 {top_hour} 点附近学习，建议保持固定节奏，先学后练。"

        return "最近学习节奏已经开始积累，但还需要更多真实记录才能形成稳定习惯画像。"

    def _save_report(self, user_id: int, report_type: str, content_json: dict[str, Any]) -> None:
        report = LearningReport(
            user_id=user_id,
            report_type=report_type,
            content_json=content_json,
        )
        self.db.add(report)
        self.db.commit()

    def _get_mastery_score(self, profile: UserProfile, knowledge_point: str) -> int:
        mastery_json = profile.mastery_json if isinstance(profile.mastery_json, dict) else {}
        value = mastery_json.get(knowledge_point, {})
        if isinstance(value, dict):
            score = value.get("score", 62)
        else:
            score = value or 62
        return max(0, min(100, int(score)))

    def _parse_exercise_content(self, content: str) -> dict[str, Any]:
        try:
            payload = json.loads(content)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _infer_difficulty_level(self, question_type: str) -> int:
        if question_type in {"choice", "blank", "judge"}:
            return 1
        if question_type == "short_answer":
            return 2
        return 3

    def _map_difficulty(self, difficulty: int) -> str:
        if difficulty <= 1:
            return "foundation"
        if difficulty == 2:
            return "intermediate"
        return "advanced"

    def _label_question_type(self, question_type: str) -> str:
        return QUESTION_TYPE_LABELS.get(question_type, question_type)
