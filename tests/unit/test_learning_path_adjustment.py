"""Tests for persisted learning-path adjustment flows."""

from common.schemas.agent import LearningPathAdjustRequest, LearningPathRequest
from services.agent_service.app.services.learning_path import LearningPathService


def test_adjust_learning_path_marks_task_completed(db_session, test_user) -> None:
    """The persisted active path should support task completion updates."""

    service = LearningPathService(db_session)
    generated = service.generate_path(
        LearningPathRequest(
            user_id=test_user.id,
            subject="Python 程序设计",
            knowledge_point="Python 循环",
            daily_minutes=45,
            learner_profile={"learning_style": "visual"},
        )
    )

    task_id = generated["stages"][0]["tasks"][0]["task_id"]
    updated = service.adjust_path(
        LearningPathAdjustRequest(
            user_id=test_user.id,
            task_id=task_id,
            action="complete",
        )
    )

    assert updated is not None
    task = updated["stages"][0]["tasks"][0]
    assert task["completed"] is True
    assert task["status"] == "completed"
