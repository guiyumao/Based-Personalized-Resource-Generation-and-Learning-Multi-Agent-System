"""Tests for persisted learning-path adjustment flows."""

from common.schemas.agent import LearningPathAdjustRequest, LearningPathRequest
from services.agent_service.app.services.learning_path import LearningPathService


def _learning_path_payload(user_id: int, knowledge_point: str) -> dict[str, object]:
    return {
        "user_id": user_id,
        "subject": "Python programming",
        "knowledge_point": knowledge_point,
        "overview": "LLM generated path",
        "estimated_days": 3,
        "stages": [
            {
                "stage_id": "stage-1",
                "title": "Concepts",
                "description": "Build the core concept first.",
                "tasks": [
                    {
                        "task_id": "task-1",
                        "title": "Read courseware",
                        "task_type": "courseware",
                        "knowledge_point": knowledge_point,
                        "objective": "Understand the core concept.",
                        "estimated_minutes": 20,
                        "difficulty": "foundation",
                        "completed": False,
                        "status": "pending",
                    }
                ],
            }
        ],
    }


def test_adjust_learning_path_marks_task_completed(db_session, test_user, monkeypatch) -> None:
    from services.agent_service.app.services import plan_knowledge
    monkeypatch.setattr(plan_knowledge,"require_plan_knowledge",lambda *_:{"knowledge_point":"Python 循环","subject_id":1,"point_id":1,"published_versions":[1],"usable_chunks":[]})
    """The persisted active path should support task completion updates."""

    service = LearningPathService(db_session)
    monkeypatch.setattr(
        service,
        "_generate_path_with_llm",
        lambda request, teacher_scope: _learning_path_payload(request.user_id, request.knowledge_point),
    )
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
