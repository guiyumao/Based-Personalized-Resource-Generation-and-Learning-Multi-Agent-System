"""AURA-inspired analytics and admin directory with real local evidence."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.models.learning import (
    AnswerRecord,
    CardReviewEvent,
    ChatMessage,
    ChatSession,
    Exercise,
    KnowledgePoint,
    LearningPath,
    LearningTask,
    Resource,
    ResourceInteraction,
    ReviewCard,
    User,
)
from services.evaluation_service.app.main import app as evaluation_app
from services.evaluation_service.app.services.learning_analytics import build_learning_analytics
from services.system_service.app.main import app as system_app
from services.system_service.app.services import system_persistence


def _session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_analytics_counts_real_events_and_excludes_other_user():
    factory = _session_factory()
    with factory() as db:
        user = User(username="learner", password_hash="hash", role="student")
        other = User(username="other", password_hash="hash", role="student")
        point = KnowledgePoint(name="fractions")
        db.add_all([user, other, point])
        db.flush()
        exercise = Exercise(knowledge_point_id=point.id, type="single_choice", content="1+1", answer="2")
        resource = Resource(title="math", type="notes", content="fractions")
        db.add_all([exercise, resource])
        db.flush()
        path = LearningPath(user_id=user.id, path_data_json={}, status="active")
        db.add(path)
        db.flush()
        db.add_all([
            LearningTask(path_id=path.id, task_type="read", completed=True),
            LearningTask(path_id=path.id, task_type="practice", completed=False),
        ])
        card = ReviewCard(user_id=user.id, front="分数相加前先做什么？", back="通分")
        db.add(card)
        db.flush()
        when = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
        db.add_all([
            AnswerRecord(user_id=user.id, exercise_id=exercise.id, user_answer="2", is_correct=True, time_spent=90, created_at=when),
            AnswerRecord(user_id=user.id, exercise_id=exercise.id, user_answer="?", is_correct=None, time_spent=30, created_at=when),
            AnswerRecord(user_id=other.id, exercise_id=exercise.id, user_answer="0", is_correct=False, time_spent=500, created_at=when),
            ResourceInteraction(user_id=user.id, resource_id=resource.id, action="view", created_at=when),
            CardReviewEvent(user_id=user.id, card_id=card.id, grade=4, interval_days=1, next_due_at=when + timedelta(days=1), reviewed_at=when),
        ])
        chat = ChatSession(user_id=user.id, title="help")
        db.add(chat)
        db.flush()
        db.add(ChatMessage(session_id=chat.id, role="user", content="question", created_at=when))
        db.commit()

        result = build_learning_analytics(db, user.id)
        summary = result["summary"]
        assert summary["answers"] == 2
        assert summary["graded_answers"] == 1
        assert summary["accuracy_percent"] == 100.0
        assert summary["question_seconds"] == 120
        assert summary["resource_events"] == 1
        assert summary["questions_asked"] == 1
        assert summary["card_reviews"] == 1
        assert summary["active_days"] == 1
        assert len(result["daily"]) == 30
        assert result["knowledge_accuracy"][0]["name"] == "fractions"
        assert result["knowledge_accuracy"][0]["accuracy_percent"] == 100.0
        assert result["path_progress"]["completion_percent"] == 50.0


def test_admin_directory_redacts_password_and_dashboard_counts(monkeypatch):
    factory = _session_factory()
    monkeypatch.setattr(system_persistence, "SessionLocal", factory)
    with factory() as db:
        db.add_all([
            User(username="learner", password_hash="do-not-leak", role="student", email="a@example.com"),
            User(username="teacher", password_hash="also-secret", role="teacher", is_active=False),
        ])
        db.commit()
    manager = system_persistence.SystemManager()
    page = manager.list_users(1, 10, keyword="learn", role="student")
    assert page.total == 1
    assert page.items[0].username == "learner"
    assert "password" not in page.model_dump_json()
    assert manager.dashboard().total_users == 2
    assert manager.dashboard().active_users == 1


def test_new_routes_enforce_existing_auth(auth_headers, admin_headers, test_user, other_user):
    evaluation_client = TestClient(evaluation_app)
    system_client = TestClient(system_app)
    assert evaluation_client.get("/evaluation/analytics/1").status_code == 401
    assert evaluation_client.get(f"/evaluation/analytics/{other_user.id}", headers=auth_headers).status_code == 403
    own = evaluation_client.get(f"/evaluation/analytics/{test_user.id}", headers=auth_headers)
    assert own.status_code == 200
    assert own.json()["data"]["summary"]["answers"] == 0
    assert own.json()["data"]["knowledge_accuracy"] == []
    assert own.json()["data"]["path_progress"] is None
    assert system_client.get("/system/dashboard", headers=auth_headers).status_code == 403
    assert system_client.get("/system/users", headers=auth_headers).status_code == 403
    assert system_client.get("/system/users", headers=admin_headers).status_code == 200
    assert system_client.get("/system/dashboard", headers=admin_headers).status_code == 200
