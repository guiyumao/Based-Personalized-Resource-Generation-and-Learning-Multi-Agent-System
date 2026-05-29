"""Unit tests for the student learning workspace backend helpers."""

from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.learning_path import LearningPathService
from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


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
        type(
            "Payload",
            (),
            {
                "user_id": 1,
                "knowledge_point": "Python 循环",
                "resource_style": "interactive",
                "learner_profile": {"style": "visual"},
                "exercise_count": 5,
            },
        )()
    )

    assert response["knowledge_point"] == "Python 循环"
    assert len(response["exercises"]) == 5
    assert response["exercises"][0]["prompt"]


def test_practice_submission_returns_feedback() -> None:
    """Practice submissions should produce immediate evaluation feedback."""

    service = ReportService()
    feedback = service.evaluate_practice(
        PracticeSubmission(
            user_id=1,
            exercise_id=1,
            knowledge_point="Python 循环",
            question_type="choice",
            user_answer="B",
            correct_answer="B",
            analysis="循环用于重复执行。",
            time_spent=12,
        )
    )

    assert feedback.is_correct is True
    assert feedback.score == 100
