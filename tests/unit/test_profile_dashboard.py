"""Unit tests for learner profile dashboard helpers."""

import asyncio

from fastapi.testclient import TestClient

from teaching_fixtures import registered_catalog  # noqa: F401

from common.models.learning import (
    AnswerRecord,
    Exercise,
    KnowledgePoint,
    Resource,
    ResourceInteraction,
    UserProfile,
)
from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService
from services.user_service.app.main import app as user_app


class FakePublisher:
    """No-op publisher for tests that should not touch external queues."""

    def publish(self, queue_name: str, message: dict[str, object]) -> None:
        return None


def test_transcript_summary_does_not_count_as_zero_mastery() -> None:
    profile = UserProfile(
        user_id=1,
        mastery_json={
            "Python loops": {"score": 80},
            "transcript": {"analysis_id": 7, "weak_subjects": ["数学"]},
        },
        learning_style="",
        cognitive_abilities={},
        habits={},
    )
    snapshot = ReportService(publisher=FakePublisher())._build_profile_snapshot(1, [], profile)
    assert snapshot["mastery_overview"] is None
    assert snapshot["heatmap"] == []


def test_profile_snapshot_contains_radar_and_heatmap(db_session, test_user) -> None:
    """Profile snapshot should expose dashboard-ready radar and heatmap data."""

    async def run() -> None:
        service = ReportService(publisher=FakePublisher())
        await service.evaluate_practice(
            PracticeSubmission(
                user_id=test_user.id,
                exercise_id=110000 + test_user.id,
                knowledge_point="Python loops",
                question_type="choice",
                user_answer="B",
                correct_answer="B",
                analysis="Loops repeat a task according to a condition.",
                time_spent=15,
            )
        )

        snapshot = await service.generate_profile_snapshot(test_user.id)

        assert snapshot["mastery_overview"] is None
        assert snapshot["radar_metrics"]
        assert snapshot["heatmap"] == []

    asyncio.run(run())


def test_dashboard_profile_uses_own_studied_topics_when_evaluation_is_unavailable(
    db_session, test_user, other_user, auth_headers, monkeypatch
) -> None:
    """Content is built from real submissions, scoped to the learner, even during service failure."""

    async def submit(user_id: int, exercise_id: int, topic: str, correct: bool) -> None:
        await ReportService(publisher=FakePublisher()).evaluate_practice(
            PracticeSubmission(
                user_id=user_id,
                exercise_id=exercise_id,
                knowledge_point=topic,
                question_type="choice",
                user_answer="B" if correct else "A",
                correct_answer="B",
                analysis="practice feedback",
                time_spent=15,
            )
        )

    asyncio.run(submit(test_user.id, 220000 + test_user.id, "Python 循环", True))
    asyncio.run(submit(test_user.id, 230000 + test_user.id, "Python 循环", False))
    other_exercise_id = 240000 + other_user.id
    asyncio.run(submit(other_user.id, other_exercise_id, "数据库索引", True))

    def unavailable(*args, **kwargs):
        raise ConnectionError("evaluation unavailable")

    monkeypatch.setattr("services.user_service.app.api.routes.users.httpx.get", unavailable)
    try:
        response = TestClient(user_app).get(
            f"/users/{test_user.id}/profile/dashboard", headers=auth_headers
        )
        assert response.status_code == 200
        content = response.json()["learning_content"]
        assert content["total_answers"] == 2
        assert content["accuracy"] == 50
        assert content["knowledge_point_count"] == 1
        assert content["knowledge_points"][0]["name"] == "Python 循环"
        assert content["knowledge_points"][0]["wrong"] == 1
        assert "数据库索引" not in str(content)
    finally:
        db_session.query(AnswerRecord).filter(AnswerRecord.user_id == other_user.id).delete()
        db_session.query(Exercise).filter(Exercise.id == other_exercise_id).delete()
        db_session.commit()


def test_empty_dashboard_has_no_invented_ability_scores(db_session, test_user, auth_headers, monkeypatch) -> None:
    db_session.add(UserProfile(user_id=test_user.id, mastery_json={}, learning_style="", cognitive_abilities={}, habits={}))
    db_session.commit()
    monkeypatch.setattr(
        "services.user_service.app.api.routes.users.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    response = TestClient(user_app).get(
        f"/users/{test_user.id}/profile/dashboard", headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["radar_metrics"] == []
    assert payload["learning_content"]["total_answers"] == 0
    assert payload["learning_content"]["accuracy"] is None


def test_resource_view_appears_as_exploration_without_mastery(
    db_session, test_user, auth_headers, monkeypatch
) -> None:
    db_session.add(UserProfile(user_id=test_user.id, mastery_json={}, learning_style="", cognitive_abilities={}, habits={}))
    point = KnowledgePoint(name=f"Python 函数 {test_user.id}")
    db_session.add(point)
    db_session.flush()
    resource = Resource(type="courseware", content="函数学习资料", knowledge_point_id=point.id)
    db_session.add(resource)
    db_session.flush()
    db_session.add(ResourceInteraction(user_id=test_user.id, resource_id=resource.id, action="view", knowledge_point=point.name))
    db_session.commit()
    monkeypatch.setattr(
        "services.user_service.app.api.routes.users.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    try:
        response = TestClient(user_app).get(
            f"/users/{test_user.id}/profile/dashboard", headers=auth_headers
        )
        assert response.status_code == 200
        content = response.json()["learning_content"]
        assert content["total_answers"] == 0
        assert content["accuracy"] is None
        assert content["knowledge_points"] == []
        assert content["explored_points"] == [{"name": point.name, "interactions": 1}]
    finally:
        db_session.query(ResourceInteraction).filter(ResourceInteraction.user_id == test_user.id).delete()
        db_session.delete(resource)
        db_session.delete(point)
        db_session.commit()
