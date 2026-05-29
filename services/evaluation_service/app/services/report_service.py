"""In-memory evaluation and report service for the current project stage."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from services.evaluation_service.app.schemas.report import (
    AnswerRecordIn,
    LatestMistakeEvidence,
    MistakeItem,
    MistakeNotebook,
    PracticeFeedback,
    PracticeSubmission,
    RemedialExerciseSet,
    ReportDetail,
    ReportEvidence,
    ReportSummary,
)


QUESTION_TYPE_LABELS = {
    "choice": "选择题",
    "blank": "填空题",
    "judge": "判断题",
    "short_answer": "简答题",
    "programming": "编程题",
}


@dataclass
class PracticeTrace:
    """One evaluated practice trace kept for reporting."""

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


class ReportService:
    """Report generator backed by in-memory practice traces."""

    def __init__(self) -> None:
        self._answers: list[AnswerRecordIn] = []
        self._mistakes: list[MistakeItem] = []
        self._practice_traces: list[PracticeTrace] = []

    def submit_answer(self, payload: AnswerRecordIn) -> AnswerRecordIn:
        """Store one answer record."""

        self._answers.append(payload)
        return payload

    def evaluate_practice(self, payload: PracticeSubmission) -> PracticeFeedback:
        """Evaluate one practice submission and return immediate feedback."""

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

        self._answers.append(
            AnswerRecordIn(
                user_id=payload.user_id,
                exercise_id=payload.exercise_id,
                answer=payload.user_answer,
                is_correct=is_correct,
                time_spent=payload.time_spent,
            )
        )
        self._practice_traces.append(
            PracticeTrace(
                user_id=payload.user_id,
                exercise_id=payload.exercise_id,
                knowledge_point=payload.knowledge_point,
                question_type=payload.question_type,
                user_answer=payload.user_answer,
                correct_answer=payload.correct_answer,
                analysis=payload.analysis,
                is_correct=is_correct,
                time_spent=payload.time_spent,
                score=score,
            )
        )

        if is_correct:
            feedback = "回答正确，这一题的核心思路已经掌握。"
            suggested_action = "继续下一题，保持当前节奏。"
        else:
            feedback = "这道题没有答对，建议先看解析，再复述思路后进入变式重练。"
            suggested_action = "优先处理同知识点错题，特别关注题目中的边界条件和步骤表达。"
            self._mistakes.append(
                MistakeItem(
                    user_id=payload.user_id,
                    exercise_id=payload.exercise_id,
                    knowledge_point=payload.knowledge_point,
                    question_type=payload.question_type,
                    user_answer=payload.user_answer,
                    correct_answer=payload.correct_answer,
                    analysis=payload.analysis,
                    suggested_action=suggested_action,
                )
            )

        return PracticeFeedback(
            user_id=payload.user_id,
            exercise_id=payload.exercise_id,
            is_correct=is_correct,
            score=score,
            feedback=feedback,
            suggested_action=suggested_action,
            analysis=payload.analysis,
        )

    def generate_stage_report(self, user_id: int) -> ReportSummary:
        """Create a stage report summary for a user."""

        traces = self._get_user_traces(user_id)
        evidence = self._build_evidence(traces, user_id)
        return ReportSummary(
            report_type="stage",
            user_id=user_id,
            title="阶段学习报告",
            summary=(
                f"当前阶段共完成 {evidence.total_answers} 次作答，"
                f"正确率约为 {evidence.accuracy}%。"
            ),
        )

    def generate_stage_report_detail(self, user_id: int) -> ReportDetail:
        """Create a detailed stage report for the student workspace."""

        traces = self._get_user_traces(user_id)
        evidence = self._build_evidence(traces, user_id)
        if not traces:
            return ReportDetail(
                report_type="stage",
                user_id=user_id,
                title="阶段学习报告",
                summary="当前还没有作答记录，完成一轮练习后这里会出现具体反馈。",
                strengths=["开始练习后，这里会显示你当前阶段已经稳定掌握的能力。"],
                weaknesses=["开始练习后，这里会指出你当前最需要补强的题型和知识点。"],
                next_actions=["先完成一组练习题，再回来看阶段反馈。"],
                evidence=evidence,
            )

        strengths = [
            f"本阶段共答题 {evidence.total_answers} 次，其中答对 {evidence.correct_answers} 次，整体正确率为 {evidence.accuracy}%。",
            f"平均每题耗时约 {evidence.average_time_spent} 秒，说明你当前的作答节奏已经有了可跟踪的数据基础。",
        ]
        if evidence.strongest_question_types:
            strengths.append(f"当前表现相对稳定的题型：{'、'.join(evidence.strongest_question_types[:3])}。")
        else:
            strengths.append("目前还在积累基础作答数据，继续练习后会更容易识别稳定强项。")

        weaknesses: list[str] = []
        if evidence.weakest_knowledge_point and evidence.weakest_knowledge_accuracy is not None:
            weaknesses.append(
                f"当前最薄弱的知识点是 {evidence.weakest_knowledge_point}，该知识点正确率仅为 {evidence.weakest_knowledge_accuracy}%。"
            )
        if evidence.weakest_question_types:
            weaknesses.append(f"当前错误更集中的题型是：{'、'.join(evidence.weakest_question_types[:3])}。")
        else:
            weaknesses.append("当前没有明显单一弱项题型，但仍需继续通过更多题目稳定表现。")
        if evidence.latest_mistake is not None:
            weaknesses.append(
                f"最近一次错题出现在 {evidence.latest_mistake.knowledge_point} / "
                f"{self._label_question_type(evidence.latest_mistake.question_type)}，"
                f"暴露的问题是：{evidence.latest_mistake.analysis}"
            )

        next_actions = []
        if evidence.weakest_knowledge_point:
            next_actions.append(f"优先重练 {evidence.weakest_knowledge_point} 相关题目，先做同类题再做变式题。")
        if evidence.weakest_question_types:
            next_actions.append(f"下一轮练习重点补强 {'、'.join(evidence.weakest_question_types[:2])}。")
        next_actions.append("每道错题先看标准答案与解析，再用自己的话复述一遍解题步骤。")

        return ReportDetail(
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

    def generate_comprehensive_report(self, user_id: int) -> ReportSummary:
        """Create a comprehensive report summary for a user."""

        traces = self._get_user_traces(user_id)
        evidence = self._build_evidence(traces, user_id)
        return ReportSummary(
            report_type="comprehensive",
            user_id=user_id,
            title="综合学习报告",
            summary=(
                f"累计作答 {evidence.total_answers} 次，综合正确率约为 {evidence.accuracy}%。"
            ),
        )

    def generate_comprehensive_report_detail(self, user_id: int) -> ReportDetail:
        """Create a detailed comprehensive report."""

        traces = self._get_user_traces(user_id)
        evidence = self._build_evidence(traces, user_id)
        if not traces:
            return ReportDetail(
                report_type="comprehensive",
                user_id=user_id,
                title="综合学习报告",
                summary="当前还没有足够的作答记录，完成练习后会生成综合趋势反馈。",
                strengths=["开始积累练习记录后，这里会显示你的长期优势。"],
                weaknesses=["开始积累练习记录后，这里会显示重复出现的薄弱点。"],
                next_actions=["先完成基础练习，再回来查看综合报告。"],
                evidence=evidence,
            )

        strengths = [
            f"累计完成 {evidence.total_answers} 次作答，综合正确率 {evidence.accuracy}%，平均得分 {evidence.average_score} 分。",
        ]
        if evidence.strongest_question_types:
            strengths.append(f"当前表现最好的题型是 {'、'.join(evidence.strongest_question_types[:2])}。")
        if evidence.accuracy >= 70:
            strengths.append("整体表现已经进入较稳定区间，可以逐步增加进阶题比例。")
        else:
            strengths.append("虽然整体正确率还在爬升，但已经积累了足够的作答数据，可用于精准补弱。")

        weaknesses = [
            f"当前累计错题 {evidence.mistake_count} 道，平均每题耗时约 {evidence.average_time_spent} 秒。",
        ]
        if evidence.weakest_knowledge_point and evidence.weakest_knowledge_accuracy is not None:
            weaknesses.append(
                f"综合来看最需要补强的知识点是 {evidence.weakest_knowledge_point}，正确率为 {evidence.weakest_knowledge_accuracy}%。"
            )
        if evidence.weakest_question_types:
            weaknesses.append(
                f"当前更容易失分或耗时偏高的题型是：{'、'.join(evidence.weakest_question_types[:3])}。"
            )

        next_actions = []
        if evidence.weakest_knowledge_point:
            next_actions.append(f"接下来优先围绕 {evidence.weakest_knowledge_point} 连续完成 1 组专项练习。")
        if evidence.weakest_question_types:
            next_actions.append(f"针对 {'、'.join(evidence.weakest_question_types[:2])} 做限时训练，提升作答结构化程度。")
        next_actions.append("保持“作答 -> 看标准答案 -> 复述解析 -> 做变式题”的固定复盘流程。")

        return ReportDetail(
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

    def get_mistake_statistics(self, user_id: int) -> dict[str, object]:
        """Return mistake statistics for a user."""

        mistakes = [item for item in self._answers if item.user_id == user_id and item.is_correct is False]
        return {
            "user_id": user_id,
            "mistake_count": len(mistakes),
            "exercise_ids": [item.exercise_id for item in mistakes],
        }

    def get_mistake_notebook(self, user_id: int) -> MistakeNotebook:
        """Return the learner mistake notebook."""

        items = [item for item in self._mistakes if item.user_id == user_id]
        return MistakeNotebook(
            user_id=user_id,
            mistake_count=len(items),
            items=items,
        )

    def generate_remedial_exercises(self, user_id: int) -> RemedialExerciseSet:
        """Generate variant exercises based on the user's mistakes."""

        mistakes = [item for item in self._mistakes if item.user_id == user_id]
        exercises: list[dict[str, object]] = []

        for index, item in enumerate(mistakes, start=1):
            exercises.append(
                {
                    "exercise_id": 9000 + index,
                    "knowledge_point": item.knowledge_point,
                    "question_type": item.question_type,
                    "prompt": (
                        f"变式题 {index}：围绕 {item.knowledge_point} 重新完成一题，"
                        f"重点避免上次暴露出的错误：{item.analysis}"
                    ),
                    "options": [
                        "A. 关注边界条件",
                        "B. 按步骤拆解逻辑",
                        "C. 检查循环或判断条件",
                        "D. 对照示例验证结果",
                    ]
                    if item.question_type == "choice"
                    else [],
                    "answer": item.correct_answer,
                    "analysis": f"这是一道针对错题的变式练习，目标是巩固 {item.knowledge_point} 并修正上次错误。",
                    "source_exercise_id": item.exercise_id,
                }
            )

        return RemedialExerciseSet(
            user_id=user_id,
            generated_from_mistakes=len(mistakes),
            summary="已根据错题本自动生成变式重练题目。",
            exercises=exercises,
        )

    def generate_profile_snapshot(self, user_id: int) -> dict[str, object]:
        """Generate a learner dashboard snapshot from current answer behavior."""

        traces = self._get_user_traces(user_id)
        total_count = len(traces)
        correct_count = sum(1 for item in traces if item.is_correct)
        average_time = round(sum(item.time_spent for item in traces) / total_count) if total_count else 0
        accuracy = round((correct_count / total_count) * 100) if total_count else 62
        mistake_count = len([item for item in self._mistakes if item.user_id == user_id])

        logical_score = min(95, max(45, accuracy))
        stability_score = min(92, max(40, 88 - mistake_count * 6))
        speed_score = min(90, max(35, 85 - max(0, average_time - 20)))
        reflection_score = min(96, max(42, 78 - mistake_count * 3 + correct_count * 2))

        return {
            "user_id": user_id,
            "learning_style": "视觉型 + 练习驱动",
            "mastery_overview": accuracy,
            "weekly_focus_minutes": max(45, total_count * 18),
            "habit_summary": "最近以晚间学习为主，适合先看案例再刷题巩固。",
            "radar_metrics": [
                {"dimension": "知识掌握", "score": accuracy},
                {"dimension": "逻辑分析", "score": logical_score},
                {"dimension": "作答稳定性", "score": stability_score},
                {"dimension": "完成速度", "score": speed_score},
                {"dimension": "复盘反思", "score": reflection_score},
            ],
            "heatmap": [
                {"knowledge_point": "Python 循环", "mastery": accuracy},
                {"knowledge_point": "条件判断", "mastery": max(35, accuracy - 8)},
                {"knowledge_point": "列表与字典", "mastery": min(94, accuracy + 6)},
                {"knowledge_point": "函数封装", "mastery": max(30, accuracy - 5)},
                {"knowledge_point": "综合应用", "mastery": max(28, accuracy - 12)},
            ],
        }

    def _build_evidence(self, traces: list[PracticeTrace], user_id: int) -> ReportEvidence:
        total_answers = len(traces)
        correct_answers = sum(1 for item in traces if item.is_correct)
        average_time_spent = round(sum(item.time_spent for item in traces) / total_answers) if total_answers else 0
        average_score = round(sum(item.score for item in traces) / total_answers) if total_answers else 0
        accuracy = round((correct_answers / total_answers) * 100) if total_answers else 0
        type_stats = self._build_question_type_stats(traces)
        strong_types = [name for name, stats in type_stats.items() if stats["accuracy"] >= 80]
        weak_types = [name for name, stats in type_stats.items() if stats["accuracy"] < 60]
        labeled_strong_types = [self._label_question_type(name) for name in strong_types]
        labeled_weak_types = [self._label_question_type(name) for name in weak_types]
        knowledge_point_stats = self._build_knowledge_point_stats(traces)
        weakest_knowledge_point = self._pick_weakest_item(knowledge_point_stats)
        weakest_knowledge_accuracy = (
            knowledge_point_stats[weakest_knowledge_point]["accuracy"]
            if weakest_knowledge_point is not None
            else None
        )
        latest_mistake = self._get_latest_mistake(user_id)

        return ReportEvidence(
            total_answers=total_answers,
            correct_answers=correct_answers,
            accuracy=accuracy,
            average_time_spent=average_time_spent,
            average_score=average_score,
            mistake_count=len([item for item in self._mistakes if item.user_id == user_id]),
            strongest_question_types=labeled_strong_types,
            weakest_question_types=labeled_weak_types,
            weakest_knowledge_point=weakest_knowledge_point,
            weakest_knowledge_accuracy=weakest_knowledge_accuracy,
            latest_mistake=LatestMistakeEvidence(
                knowledge_point=latest_mistake.knowledge_point,
                question_type=latest_mistake.question_type,
                user_answer=latest_mistake.user_answer,
                correct_answer=latest_mistake.correct_answer,
                analysis=latest_mistake.analysis,
            )
            if latest_mistake is not None
            else None,
        )

    def _get_user_traces(self, user_id: int) -> list[PracticeTrace]:
        return [item for item in self._practice_traces if item.user_id == user_id]

    def _calculate_accuracy(self, traces: list[PracticeTrace]) -> int:
        if not traces:
            return 0
        return round(sum(1 for item in traces if item.is_correct) / len(traces) * 100)

    def _build_question_type_stats(self, traces: list[PracticeTrace]) -> dict[str, dict[str, int]]:
        grouped: dict[str, list[PracticeTrace]] = defaultdict(list)
        for item in traces:
            grouped[item.question_type].append(item)

        stats: dict[str, dict[str, int]] = {}
        for question_type, items in grouped.items():
            stats[question_type] = {
                "count": len(items),
                "correct": sum(1 for entry in items if entry.is_correct),
                "accuracy": round(sum(1 for entry in items if entry.is_correct) / len(items) * 100),
                "avg_time": round(sum(entry.time_spent for entry in items) / len(items)),
            }
        return stats

    def _build_knowledge_point_stats(self, traces: list[PracticeTrace]) -> dict[str, dict[str, int]]:
        grouped: dict[str, list[PracticeTrace]] = defaultdict(list)
        for item in traces:
            grouped[item.knowledge_point].append(item)

        stats: dict[str, dict[str, int]] = {}
        for knowledge_point, items in grouped.items():
            stats[knowledge_point] = {
                "count": len(items),
                "correct": sum(1 for entry in items if entry.is_correct),
                "accuracy": round(sum(1 for entry in items if entry.is_correct) / len(items) * 100),
            }
        return stats

    def _pick_weakest_item(self, stats: dict[str, dict[str, int]]) -> str | None:
        if not stats:
            return None
        return sorted(stats.items(), key=lambda item: (item[1]["accuracy"], item[1]["count"]))[0][0]

    def _get_latest_mistake(self, user_id: int) -> MistakeItem | None:
        mistakes = [item for item in self._mistakes if item.user_id == user_id]
        return mistakes[-1] if mistakes else None

    def _label_question_type(self, question_type: str) -> str:
        return QUESTION_TYPE_LABELS.get(question_type, question_type)
