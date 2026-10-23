import json
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
from services.user_service.app.services import learning_style_inference as inference_module


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


# ── Model-generated style axes ──────────────────────────────────


def _seed_answer(db) -> None:
    db.add(
        AnswerRecord(
            user_id=1,
            exercise_id=1,
            user_answer="A",
            is_correct=True,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    db.commit()


def _patch_model(monkeypatch, model) -> None:
    monkeypatch.setattr(
        inference_module,
        "LLMFactory",
        lambda *_: SimpleNamespace(build_chat_model=lambda **__: model),
    )


class _Model:
    def __init__(self, payload):
        self.calls = 0
        self.payload = payload

    def invoke(self, _messages):
        self.calls += 1
        content = (
            self.payload
            if isinstance(self.payload, str)
            else json.dumps(self.payload, ensure_ascii=False)
        )
        return SimpleNamespace(content=content)


def test_model_inference_fills_axes_and_manual_values_win(runtime, monkeypatch):
    db, _, client = runtime
    _seed_answer(db)
    model = _Model(
        {
            "axes": {
                "processing": {"value": "0.5", "confidence": "0.8", "evidence": "多次先动手试错"},
                "perception": {"value": None, "confidence": 0.2, "evidence": "记录不足"},
                "input": {"value": 0.6, "confidence": 0.7, "evidence": "偏好图解资源"},
                "understanding": {"value": -0.4, "confidence": 0.5, "evidence": "先看整体框架"},
            },
            "summary": "偏活跃与视觉，理解偏全局",
        }
    )
    _patch_model(monkeypatch, model)

    original = client.get("/users/1/learning-portrait").json()
    assert original["inference"]["status"] == "never"
    saved = client.put(
        "/users/1/learning-portrait",
        json={"expected_updated_at": original["updated_at"], "axes": {"input": 0.7}},
    )
    assert saved.status_code == 200

    result = client.post("/users/1/learning-portrait/infer", json={}).json()
    assert result["status"] == "completed", result
    assert model.calls == 1
    assert result["snapshot"]["inference"]["status"] == "completed"

    read = client.get("/users/1/learning-portrait").json()
    axes = {axis["key"]: axis for axis in read["axes"]}
    assert axes["input"]["value"] == 0.7
    assert axes["input"]["source"] == "user_reported"
    assert axes["processing"]["value"] == 0.5
    assert axes["processing"]["source"] == "model_inferred"
    assert axes["processing"]["confidence"] == 0.8
    assert axes["processing"]["evidence"] == "多次先动手试错"
    assert axes["perception"]["value"] is None and axes["perception"]["source"] == "missing"
    assert axes["understanding"]["source"] == "model_inferred"
    assert read["inference"]["status"] == "completed"
    assert read["inference"]["stale"] is False
    assert read["inference"]["summary"] == "偏活跃与视觉，理解偏全局"
    assert "1 项本人自述" in read["style_source"] and "2 项由模型" in read["style_source"]
    assert db.get(UserProfile, 1).habits["keep"] is True

    cached = client.post("/users/1/learning-portrait/infer", json={}).json()
    assert cached["status"] == "completed" and cached["cached"] is True
    assert model.calls == 1


def test_inference_rejects_invalid_or_out_of_range_output(runtime, monkeypatch):
    db, _, client = runtime
    _seed_answer(db)
    for payload in (
        "not json",
        {
            "axes": {
                "processing": {"value": 2, "confidence": 0.8, "evidence": "超出范围"},
                "perception": {"value": None, "confidence": 0.2, "evidence": ""},
                "input": {"value": 0.6, "confidence": 0.7, "evidence": ""},
                "understanding": {"value": -0.4, "confidence": 0.5, "evidence": ""},
            }
        },
    ):
        model = _Model(payload)
        _patch_model(monkeypatch, model)
        result = client.post("/users/1/learning-portrait/infer", json={}).json()
        assert result["status"] == "failed"
        read = client.get("/users/1/learning-portrait").json()
        assert read["inference"]["status"] == "never"
        assert all(axis["value"] is None for axis in read["axes"])


def test_inference_without_evidence_does_not_call_the_model(runtime, monkeypatch):
    _, _, client = runtime
    model = _Model({"axes": {}})
    _patch_model(monkeypatch, model)
    result = client.post("/users/1/learning-portrait/infer", json={}).json()
    assert result["status"] == "insufficient"
    assert model.calls == 0
    assert client.get("/users/1/learning-portrait").json()["inference"]["status"] == "never"


def test_inference_without_model_credentials_is_blocked(runtime, monkeypatch):
    db, _, client = runtime
    _seed_answer(db)

    def factory(*_args, **_kwargs):
        raise ValueError("No LLM credentials configured.")

    monkeypatch.setattr(inference_module, "LLMFactory", factory)
    result = client.post("/users/1/learning-portrait/infer", json={}).json()
    assert result["status"] == "blocked"
    assert "模型服务" in result["message"]
    assert "learning_style_inference" not in db.get(UserProfile, 1).habits


def test_manual_complete_portrait_skips_the_model(runtime, monkeypatch):
    _, _, client = runtime
    model = _Model({"axes": {}})
    _patch_model(monkeypatch, model)
    original = client.get("/users/1/learning-portrait").json()
    saved = client.put(
        "/users/1/learning-portrait",
        json={
            "expected_updated_at": original["updated_at"],
            "axes": {"processing": 0.2, "perception": 0.3, "input": 0.4, "understanding": 0.5},
        },
    )
    assert saved.status_code == 200
    result = client.post("/users/1/learning-portrait/infer", json={}).json()
    assert result["status"] == "completed" and result["skipped"] is True
    assert model.calls == 0


def test_inference_is_scoped_to_the_owner(runtime):
    _, _, client = runtime
    assert client.post("/users/2/learning-portrait/infer", json={}).status_code == 403

