"""Unit tests for the evaluation service."""

from __future__ import annotations

import asyncio

from services.evaluation_service.app.schemas.report import (
    AnswerRecordSubmission,
    PracticeSubmission,
)
from services.evaluation_service.app.services.report_service import ReportService


class FakeLLMClient:
    """Deterministic async LLM stub for evaluation tests."""

    def __init__(self) -> None:
        self.stage_calls: list[dict[str, object]] = []
        self.monthly_calls: list[dict[str, object]] = []

    async def score_subjective(self, **_: object) -> dict[str, object]:
        return {
            "score": 7.0,
            "comment": "关键点基本完整",
            "suggestion": "补充边界条件说明",
        }

    async def generate_stage_report(self, **kwargs: object) -> str:
        self.stage_calls.append(kwargs)
        return "本章节整体表现稳定。\n\n建议优先复习循环边界。"

    async def generate_monthly_report(self, **kwargs: object) -> str:
        self.monthly_calls.append(kwargs)
        return "本月进步明显，继续保持练习频率，优先补强循环边界。"


class FakePublisher:
    """Capture outbound queue events for assertions."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, object]]] = []

    def publish(self, queue_name: str, message: dict[str, object]) -> None:
        self.messages.append((queue_name, message))


def test_objective_submission_creates_mistake_notebook_entry(test_user) -> None:
    """Wrong objective answers should be persisted and appear in the notebook."""

    async def run() -> None:
        service = ReportService(llm_client=FakeLLMClient(), publisher=FakePublisher())
        result = await service.submit_answer(
            AnswerRecordSubmission(
                user_id=str(test_user.id),
                exercise_id=f"objective-{test_user.id}",
                user_answer="if",
                time_spent=12,
                knowledge_point_ids=[f"loop-{test_user.id}"],
                exercise_type="fill",
                difficulty="basic",
                standard_answer="for",
                exercise_content="填写 Python 中的循环关键字。",
                explanation="for 用于确定次数的循环。",
                chapter_id=f"chapter-{test_user.id}",
                chapter_name="Python 基础",
            )
        )
        notebook = await service.get_mistake_notebook(test_user.id)

        assert result.is_correct is False
        assert notebook.mistake_count == 1
        assert notebook.items[0].knowledge_point == f"loop-{test_user.id}"

    asyncio.run(run())


def test_subjective_submission_uses_llm_score_threshold(test_user) -> None:
    """Subjective scoring should use the LLM score and threshold to determine correctness."""

    async def run() -> None:
        service = ReportService(llm_client=FakeLLMClient(), publisher=FakePublisher())
        result = await service.submit_answer(
            AnswerRecordSubmission(
                user_id=str(test_user.id),
                exercise_id=f"subjective-{test_user.id}",
                user_answer="先遍历数组，再判断边界。",
                time_spent=210,
                knowledge_point_ids=[f"algorithm-{test_user.id}"],
                exercise_type="short_answer",
                difficulty="intermediate",
                reference_answer="说明遍历、边界判断和终止条件。",
                max_score=10,
                exercise_content="请说明线性扫描的核心步骤。",
                explanation="需要覆盖遍历顺序、边界和终止条件。",
                chapter_id=f"chapter-{test_user.id}",
                chapter_name="算法基础",
            )
        )
        assert result.is_correct is True
        assert result.score == 7.0
        assert result.ratio == 0.7
        assert result.comment == "关键点基本完整"

    asyncio.run(run())


def test_clear_mistake_notebook_hides_existing_entries_but_keeps_history(test_user) -> None:
    """Clearing the notebook should hide old mistakes without deleting answer history."""

    async def run() -> None:
        service = ReportService(llm_client=FakeLLMClient(), publisher=FakePublisher())
        knowledge_point = f"loop-{test_user.id}"

        await service.submit_answer(
            AnswerRecordSubmission(
                user_id=str(test_user.id),
                exercise_id=f"clearable-{test_user.id}",
                user_answer="if",
                time_spent=10,
                knowledge_point_ids=[knowledge_point],
                exercise_type="fill",
                difficulty="basic",
                standard_answer="for",
                exercise_content="填写循环关键字。",
                explanation="for 用于确定次数的循环。",
                chapter_id=f"chapter-{test_user.id}",
                chapter_name="Python 基础",
            )
        )

        notebook_before = await service.get_mistake_notebook(test_user.id)
        clear_result = await service.clear_mistake_notebook(test_user.id)
        notebook_after = await service.get_mistake_notebook(test_user.id)
        traces_after, _, _ = await asyncio.to_thread(service._load_user_context, test_user.id)

        assert notebook_before.mistake_count == 1
        assert clear_result.cleared_count == 1
        assert notebook_after.mistake_count == 0
        assert sum(1 for item in traces_after if not item.is_correct) == 1

        await service.submit_answer(
            AnswerRecordSubmission(
                user_id=str(test_user.id),
                exercise_id=f"new-mistake-{test_user.id}",
                user_answer="while",
                time_spent=11,
                knowledge_point_ids=[knowledge_point],
                exercise_type="fill",
                difficulty="basic",
                standard_answer="for",
                exercise_content="再次填写循环关键字。",
                explanation="新错题应在清空后重新出现。",
                chapter_id=f"chapter-{test_user.id}",
                chapter_name="Python 基础",
            )
        )
        notebook_after_new_mistake = await service.get_mistake_notebook(test_user.id)

        assert notebook_after_new_mistake.mistake_count == 1
        assert notebook_after_new_mistake.items[0].user_answer == "while"

    asyncio.run(run())


def test_three_consecutive_errors_mark_weak_point_and_emit_events(test_user) -> None:
    """Three consecutive errors on one knowledge point should mark it weak and trigger events."""

    async def run() -> None:
        publisher = FakePublisher()
        service = ReportService(llm_client=FakeLLMClient(), publisher=publisher)
        knowledge_point = f"condition-{test_user.id}"

        for attempt in range(3):
            result = await service.submit_answer(
                AnswerRecordSubmission(
                    user_id=str(test_user.id),
                    exercise_id=f"weak-{test_user.id}-{attempt}",
                    user_answer="A",
                    time_spent=9,
                    knowledge_point_ids=[knowledge_point],
                    exercise_type="choice",
                    difficulty="basic",
                    standard_answer="B",
                    exercise_content="判断条件分支的输出。",
                    explanation="需要先判断条件再选择分支。",
                    chapter_id=f"chapter-{test_user.id}",
                    chapter_name="条件判断",
                )
            )
        assert knowledge_point in result.weak_knowledge_points
        assert any(queue == "profile_updates" for queue, _ in publisher.messages)
        assert any(queue == "path_adjustments" for queue, _ in publisher.messages)

    asyncio.run(run())


def test_stage_and_monthly_reports_are_generated_from_real_history(test_user) -> None:
    """Reports should aggregate persisted answers instead of fabricated data."""

    async def run() -> None:
        llm = FakeLLMClient()
        service = ReportService(llm_client=llm, publisher=FakePublisher())
        chapter_id = f"chapter-{test_user.id}"

        await service.evaluate_practice(
            PracticeSubmission(
                user_id=test_user.id,
                exercise_id=100000 + test_user.id,
                knowledge_point=f"loop-{test_user.id}",
                question_type="choice",
                user_answer="B",
                correct_answer="B",
                analysis="for 循环先判断范围再进入循环体。",
                time_spent=18,
                difficulty="basic",
                chapter_id=chapter_id,
                chapter_name="循环结构",
            )
        )
        await service.evaluate_practice(
            PracticeSubmission(
                user_id=test_user.id,
                exercise_id=100100 + test_user.id,
                knowledge_point=f"loop-{test_user.id}",
                question_type="choice",
                user_answer="A",
                correct_answer="B",
                analysis="要关注循环边界。",
                time_spent=16,
                difficulty="basic",
                chapter_id=chapter_id,
                chapter_name="循环结构",
            )
        )
        await service.evaluate_practice(
            PracticeSubmission(
                user_id=test_user.id,
                exercise_id=100200 + test_user.id,
                knowledge_point=f"list-{test_user.id}",
                question_type="blank",
                user_answer="append",
                correct_answer="append",
                analysis="append 用于在末尾追加元素。",
                time_spent=14,
                difficulty="basic",
                chapter_id=f"chapter-2-{test_user.id}",
                chapter_name="列表操作",
            )
        )

        stage_report = await service.generate_stage_report(str(test_user.id), chapter_id)
        monthly_report = await service.generate_monthly_report(str(test_user.id))

        assert stage_report.total_answers == 2
        assert stage_report.chapter_name == "循环结构"
        assert llm.stage_calls
        assert monthly_report.chapters_completed == 2
        assert monthly_report.summary_text.startswith("本月进步明显")
        assert llm.monthly_calls

    asyncio.run(run())
