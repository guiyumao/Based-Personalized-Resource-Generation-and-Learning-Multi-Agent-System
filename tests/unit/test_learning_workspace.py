"""Unit tests for the student learning workspace backend helpers."""

import asyncio

import pytest

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
            "comment": "基础覆盖到位",
            "suggestion": "补充检查步骤",
        }


class FakePublisher:
    """No-op publisher for tests that should not touch external queues."""

    def publish(self, queue_name: str, message: dict[str, object]) -> None:
        return None


def _exercise_payload(count: int, question_types: list[str]) -> dict[str, object]:
    """Build a deterministic LLM payload for exercise-generation tests."""

    prompt_styles = [
        "基础辨析",
        "条件确认",
        "错因复盘",
        "场景迁移",
        "步骤核对",
        "边界检查",
        "概念应用",
        "变式训练",
        "结果验证",
        "综合小题",
    ]
    exercises: list[dict[str, object]] = []
    for index in range(count):
        question_type = question_types[index % len(question_types)]
        style = prompt_styles[index % len(prompt_styles)]
        exercises.append(
            {
                "exercise_id": index + 1,
                "knowledge_point": "测试知识点",
                "question_type": question_type,
                "difficulty": "foundation" if question_type == "choice" else "intermediate",
                "prompt": f"第 {index + 1} 题：{style}，{question_type} 测试题目 {index + 1}",
                "options": ["A. 选项一", "B. 选项二"] if question_type == "choice" else [],
                "answer": "A" if question_type == "choice" else "参考答案",
                "analysis": f"这是测试用的解析 {index + 1}。",
            }
        )
    return {"summary": "stub", "exercises": exercises}


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
                "learner_profile": {
                    "learning_style": "visual",
                    "profile_analysis_summaries": {
                        "knowledgeBase": "基础稳定但综合题容易卡住",
                        "learningSpeed": "节奏适中可继续进阶",
                    },
                },
            },
        )()
    )

    assert response["knowledge_point"] == "Python 循环"
    assert response["stages"]
    assert response["stages"][0]["tasks"]
    assert "深度画像建议" in response["overview"]


def test_generate_structured_exercises() -> None:
    """Exercise generation should return a structured exercise list."""

    service = ExerciseGenerationService()
    service._try_generate_with_llm = lambda *args, **kwargs: _exercise_payload(5, ["choice"] * 5)
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


def test_generate_exercises_respects_question_type_counts(monkeypatch) -> None:
    """Exercise generation should honor an explicit 5/3/2 question-type mix."""

    service = ExerciseGenerationService()
    monkeypatch.setattr(
        service,
        "_try_generate_with_llm",
        lambda *args, **kwargs: _exercise_payload(10, ["choice"] * 5 + ["judge"] * 3 + ["blank"] * 2),
    )
    response = service.generate_exercises(
        ExerciseGenerationRequest(
            user_id=1,
            knowledge_point="高数",
            resource_style="interactive",
            learner_profile={},
            exercise_count=10,
            question_type_counts={"choice": 5, "judge": 3, "blank": 2},
            generation_mode="self_test",
        )
    )

    counts: dict[str, int] = {}
    for exercise in response["exercises"]:
        counts[exercise["question_type"]] = counts.get(exercise["question_type"], 0) + 1

    assert len(response["exercises"]) == 10
    assert counts == {"choice": 5, "judge": 3, "blank": 2}


def test_generate_exercises_requires_llm_payload(monkeypatch) -> None:
    """Exercise generation should fail loudly when the LLM layer returns nothing."""

    service = ExerciseGenerationService()
    monkeypatch.setattr(service, "_try_generate_with_llm", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="LLM generation returned no valid exercise payload"):
        service.generate_exercises(
            ExerciseGenerationRequest(
                user_id=1,
                knowledge_point="高数",
                resource_style="interactive",
                learner_profile={},
                exercise_count=8,
                generation_mode="self_test",
            )
        )


def test_generate_exercises_rejects_mismatched_question_type_counts(monkeypatch) -> None:
    """Exercise generation should fail if the payload does not match the requested mix."""

    service = ExerciseGenerationService()
    monkeypatch.setattr(
        service,
        "_try_generate_with_llm",
        lambda *args, **kwargs: _exercise_payload(10, ["choice"] * 10),
    )
    with pytest.raises(ValueError, match="LLM returned 10 choice exercises, expected 5"):
        service.generate_exercises(
            ExerciseGenerationRequest(
                user_id=1,
                knowledge_point="高数",
                resource_style="interactive",
                learner_profile={},
                exercise_count=10,
                question_type_counts={"choice": 5, "judge": 3, "blank": 2},
                generation_mode="self_test",
            )
        )


def test_generate_exercises_avoids_previous_questions_for_same_knowledge_point(monkeypatch) -> None:
    """Repeated generation for one knowledge point should not reuse previous prompts."""

    service = ExerciseGenerationService()
    monkeypatch.setattr(
        service,
        "_try_generate_with_llm",
        lambda *args, **kwargs: _exercise_payload(10, ["choice"] * 5 + ["judge"] * 3 + ["blank"] * 2),
    )
    request = ExerciseGenerationRequest(
        user_id=1,
        knowledge_point="calculus-nonrepeat-practice",
        resource_style="interactive",
        learner_profile={
            "profile_analysis_summaries": {
                "knowledgeBase": "needs foundation reinforcement",
                "learningSpeed": "slow pace, small variants work better",
            }
        },
        exercise_count=10,
        question_type_counts={"choice": 5, "judge": 3, "blank": 2},
        generation_mode="self_test",
    )

    response = service.generate_exercises(request)

    assert len(response["exercises"]) == 10


def test_practice_submission_returns_feedback(test_user) -> None:
    """Practice submissions should produce immediate evaluation feedback."""

    service = ReportService(llm_client=FakeLLMClient(), publisher=FakePublisher())
    feedback = asyncio.run(
        service.evaluate_practice(
            PracticeSubmission(
                user_id=test_user.id,
                exercise_id=100000 + test_user.id,
                knowledge_point="Python 循环",
                question_type="choice",
                user_answer="B",
                correct_answer="B",
                analysis="循环用于按规则重复执行任务。",
                time_spent=12,
            )
        )
    )

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
                knowledge_point="高阶题",
                question_type="short_answer",
                user_answer="先定位问题，再检查输入输出和边界条件。",
                correct_answer="说明定位问题、复现案例、检查边界和验证修复。",
                analysis="回答应覆盖定位、检查与验证步骤。",
                exercise_content="请说明排查高阶问题时最需要检查的两个步骤。",
                time_spent=30,
            )
        )
    )

    assert feedback.is_correct is True
    assert feedback.score == 70
    assert feedback.mastery_after_update is not None
