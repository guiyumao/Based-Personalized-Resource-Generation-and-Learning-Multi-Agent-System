"""Unit tests for the student learning workspace backend helpers."""

import asyncio

from common.schemas.agent import ExerciseGenerationRequest
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.learning_path import LearningPathService
from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


class FakeLLMClient:
    """Deterministic LLM scoring stub for practice-submission tests."""

    async def score_subjective(self, **_: object) -> dict[str, object]:
        return {
            "score": 70.0,
            "comment": "要点基本覆盖",
            "suggestion": "补充检查步骤",
        }


class FakePublisher:
    """No-op publisher for tests that should not touch external queues."""

    def publish(self, queue_name: str, message: dict[str, object]) -> None:
        return None


def test_generate_learning_path_contains_stages() -> None:
    """Learning path generation should produce multiple stages and tasks."""

    service = LearningPathService()
    response = service.generate_path(
        type(
            "Payload",
            (),
            {
                "user_id": 1,
                "subject": "Python 程序设计",
                "knowledge_point": "Python 循环",
                "daily_minutes": 45,
                "learner_profile": {"learning_style": "visual"},
            },
        )()
    )

    assert response["knowledge_point"] == "Python 循环"
    assert response["stages"]
    assert response["stages"][0]["tasks"]


def test_generate_structured_exercises() -> None:
    """Exercise generation should return a structured exercise list."""

    service = ExerciseGenerationService()
    response = service.generate_exercises(
        ExerciseGenerationRequest(
            user_id=1,
            knowledge_point="Python 循环",
            resource_style="interactive",
            learner_profile={"learning_style": "visual"},
            exercise_count=5,
            generation_mode="self_test",
            courseware_content="## 学完后自测\n- 区分 for 和 while\n- 识别死循环原因",
        )
    )

    assert response["knowledge_point"] == "Python 循环"
    assert len(response["exercises"]) == 5
    assert response["exercises"][0]["prompt"]
    assert "personalization" in response


def test_exercise_generation_deduplicates_repeated_llm_questions(monkeypatch) -> None:
    """Repeated generated questions should be replaced with distinct variants."""

    service = ExerciseGenerationService()

    def repeated_llm_result(request, snapshot):
        return {
            "summary": "重复题测试",
            "exercises": [
                {
                    "exercise_id": index,
                    "knowledge_point": request.knowledge_point,
                    "question_type": "choice",
                    "difficulty": "foundation",
                    "prompt": "第 1 题：关于高级，下面哪一项理解最准确？",
                    "options": [
                        "A. 只看结果。",
                        "B. 同时关注对象、条件、边界和步骤。",
                        "C. 忽略过程。",
                        "D. 所有场景一样。",
                    ],
                    "answer": "B",
                    "analysis": "重复解析",
                }
                for index in range(1, 6)
            ],
        }

    monkeypatch.setattr(service, "_try_generate_with_llm", repeated_llm_result)
    response = service.generate_exercises(
        ExerciseGenerationRequest(
            user_id=1,
            knowledge_point="高级",
            resource_style="interactive",
            learner_profile={},
            exercise_count=5,
            generation_mode="self_test",
        )
    )

    prompts = [exercise["prompt"] for exercise in response["exercises"]]
    assert len(prompts) == 5
    assert len(set(prompts)) == 5


def test_practice_submission_returns_feedback(test_user) -> None:
    """Practice submissions should produce immediate evaluation feedback."""

    service = ReportService(llm_client=FakeLLMClient(), publisher=FakePublisher())
    feedback = asyncio.run(service.evaluate_practice(
        PracticeSubmission(
            user_id=test_user.id,
            exercise_id=100000 + test_user.id,
            knowledge_point="Python 循环",
            question_type="choice",
            user_answer="B",
            correct_answer="B",
            analysis="循环用于按照规则重复执行任务。",
            time_spent=12,
        )
    ))

    assert feedback.is_correct is True
    assert feedback.score == 100
    assert feedback.mastery_after_update is not None


def test_subjective_practice_submission_provides_reference_answer(test_user) -> None:
    """Short-answer practice submissions should satisfy the formal evaluation schema."""

    service = ReportService(llm_client=FakeLLMClient(), publisher=FakePublisher())
    feedback = asyncio.run(
        service.evaluate_practice(
            PracticeSubmission(
                user_id=test_user.id,
                exercise_id=110000 + test_user.id,
                knowledge_point="高级",
                question_type="short_answer",
                user_answer="先定位问题，再检查输入输出和边界条件。",
                correct_answer="说明定位问题、复现实例、检查边界和验证修复。",
                analysis="回答应覆盖定位、检查与验证步骤。",
                exercise_content="请说明排查高级问题时最需要检查的两个步骤。",
                time_spent=30,
            )
        )
    )

    assert feedback.is_correct is True
    assert feedback.score == 70
    assert feedback.mastery_after_update is not None
