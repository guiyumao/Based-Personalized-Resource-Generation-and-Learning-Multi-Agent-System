from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import (
    AnswerRecord,
    AuditLog,
    Exercise,
    KnowledgePoint,
    ReviewCard,
    StudyNote,
    User,
    UserProfile,
)
from services.evaluation_service.app.main import app as evaluation_app
from services.user_service.app.main import app as user_app


@pytest.fixture
def runtime():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all(
            [
                User(id=1, username="learner", password_hash="unused"),
                User(id=2, username="other", password_hash="unused"),
            ]
        )
        db.add(
            UserProfile(
                user_id=1,
                habits={"keep": True},
                mastery_json={},
                cognitive_abilities={},
                learning_style="",
            )
        )
        db.add(KnowledgePoint(id=1, name="分数"))
        db.add(
            Exercise(
                id=1,
                knowledge_point_id=1,
                type="choice",
                content="分数题目",
                answer="A",
                difficulty=2,
            )
        )
        db.commit()
        for app in (evaluation_app, user_app):
            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
                id=1, role="student"
            )
        yield db, TestClient(evaluation_app), TestClient(user_app)
        for app in (evaluation_app, user_app):
            app.dependency_overrides.clear()
    engine.dispose()


def test_insights_empty_and_unknown_are_not_invented(runtime):
    _, client, _ = runtime
    response = client.get("/evaluation/analytics/1/insights")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["daily"]) == 30
    assert data["summary"]["accuracy_percent"] is None
    assert data["conversation"]["questions_per_session"] is None
    assert data["quiz"]["question_type"] == []
    assert data["suggestion_source"].endswith("no model call")


def test_insights_uses_only_selected_user_and_period(runtime):
    db, client, _ = runtime
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add_all(
        [
            AnswerRecord(
                user_id=1, exercise_id=1, user_answer="A", is_correct=True, created_at=now
            ),
            AnswerRecord(
                user_id=1, exercise_id=1, user_answer="?", is_correct=None, created_at=now
            ),
            AnswerRecord(
                user_id=1,
                exercise_id=1,
                user_answer="B",
                is_correct=False,
                created_at=now - timedelta(days=60),
            ),
            AnswerRecord(
                user_id=2, exercise_id=1, user_answer="B", is_correct=False, created_at=now
            ),
            ReviewCard(user_id=1, front="复习", back="答案", due_at=now - timedelta(days=1)),
            ReviewCard(user_id=2, front="他人", back="不公开"),
            StudyNote(user_id=1, title="笔记", body="分数"),
        ]
    )
    db.commit()
    data = client.get("/evaluation/analytics/1/insights?days=7").json()["data"]
    assert data["summary"]["answers"] == 2
    assert data["summary"]["accuracy_percent"] == 100
    assert data["quiz"]["question_type"][0]["graded"] == 1
    assert data["flashcards"]["due"] == 1 and data["notes"] == 1
    assert sum(item["answers"] for item in data["answer_hours"]) == 2
    assert client.get("/evaluation/analytics/2/insights").status_code == 403
    assert client.get("/evaluation/analytics/1/insights?days=365").status_code == 422


def test_portrait_save_reload_reset_and_cas_preserve_existing_data(runtime):
    db, _, client = runtime
    original = client.get("/users/1/learning-portrait").json()
    assert all(axis["value"] is None for axis in original["axes"])
    saved = client.put(
        "/users/1/learning-portrait",
        json={
            "expected_updated_at": original["updated_at"],
            "axes": {"input": 0.7, "understanding": -0.4},
            "dimensions": {"goalOrientation": "掌握分数计算"},
        },
    )
    assert saved.status_code == 200, saved.text
    read = client.get("/users/1/learning-portrait").json()
    assert next(axis for axis in read["axes"] if axis["key"] == "input")["value"] == 0.7
    assert read["dimensions"]["goalOrientation"] == "掌握分数计算"
    assert read["dimension_sources"]["goalOrientation"] == "user_reported"
    assert db.get(UserProfile, 1).habits["keep"] is True
    assert db.query(AuditLog).filter_by(event="profile.preferences.updated").count() == 1
    assert (
        client.put(
            "/users/1/learning-portrait",
            json={"expected_updated_at": original["updated_at"], "axes": {"input": -0.5}},
        ).status_code
        == 409
    )
    reset = client.put(
        "/users/1/learning-portrait",
        json={
            "expected_updated_at": read["updated_at"],
            "axes": {"input": None},
            "dimensions": {"goalOrientation": ""},
        },
    )
    assert reset.status_code == 200
    assert next(axis for axis in reset.json()["axes"] if axis["key"] == "input")["value"] is None
    assert "goalOrientation" not in reset.json()["dimensions"]


@pytest.mark.parametrize(
    "payload", [{"axes": {"input": 9}}, {"axes": {"fake": 0}}, {"dimensions": {"unknown": "x"}}]
)
def test_portrait_rejects_invalid_and_cross_account_updates(runtime, payload):
    _, _, client = runtime
    assert client.put("/users/1/learning-portrait", json=payload).status_code == 422
    assert client.get("/users/2/learning-portrait").status_code == 403
    assert client.put("/users/2/learning-portrait", json={}).status_code == 403


def test_endpoints_require_auth(runtime):
    _, evaluation, users = runtime
    evaluation_app.dependency_overrides.pop(get_current_user)
    user_app.dependency_overrides.pop(get_current_user)
    assert evaluation.get("/evaluation/analytics/1/insights").status_code == 401
    assert users.get("/users/1/learning-portrait").status_code == 401
