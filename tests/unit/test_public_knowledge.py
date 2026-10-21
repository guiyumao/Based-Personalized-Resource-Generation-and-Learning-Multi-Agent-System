"""Fail-closed model review, no private fallback, and shared retrieval contracts."""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from common.db.base import Base
from common.models.learning import LearningPath, SystemSubject, User
from common.schemas.agent import LearningPathRequest
from services.agent_service.app.services import knowledge_bootstrap as bootstrap
from services.agent_service.app.services import plan_knowledge
from services.agent_service.app.services import public_knowledge as public
from services.agent_service.app.services.learning_path import LearningPathService


@pytest.fixture
def public_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, username="public-builder", password_hash="unused"))
        db.commit()
        yield db
    engine.dispose()


@pytest.mark.parametrize("raw", ["not json", '{"verdict":"PASS"}',
    '{"verdict":"PASS","reason":"ok","issues":["计算错误"]}',
    '{"verdict":"PASS","reason":"","issues":[]}',
    '{"verdict":"PASS","reason":"ok","issues":[],"admin_approved":true}'])
def test_invalid_review_never_approves(monkeypatch, raw):
    monkeypatch.setattr(public, "_invoke_public_model", lambda *a, **k: raw)
    assert public.review_public_content("数学", "方程", "正文")["passed"] is False


def test_review_receives_full_exact_body_and_hash(monkeypatch):
    captured = {}
    body = "正文" * 9000
    def invoke(template, data, **kwargs):
        captured.update(data)
        assert template == "public_knowledge_review.md"
        assert kwargs["stage"] == "audit"
        return json.dumps({"verdict": "PASS", "reason": "逐项检查通过", "issues": []})
    monkeypatch.setattr(public, "_invoke_public_model", invoke)
    assert public.review_public_content("数学", "方程", body)["passed"]
    assert captured["content"] == body


@pytest.mark.parametrize("verdict,reason", [("REJECT", "MODEL_REVIEW_REJECTED"), ("UNAVAILABLE", "MODEL_REVIEW_UNAVAILABLE")])
def test_no_catalog_mutations_on_review_failure(public_db, monkeypatch, verdict, reason):
    monkeypatch.setattr(public, "review_public_content", lambda *a: {
        "passed": False, "method": "llm", "verdict": verdict})
    result = bootstrap.promote_draft_to_knowledge_base(public_db, 1, "数学", "方程", {}, [])
    assert result["reason"] == reason
    assert public_db.query(SystemSubject).count() == 0


def test_failed_publication_never_generates_private_plan(public_db, monkeypatch):
    monkeypatch.setattr(public, "ensure_public_knowledge", lambda *a, **k: (_ for _ in ()).throw(
        HTTPException(503, {"code": "PUBLISH_FAILED"})))
    monkeypatch.setattr(LearningPathService, "_generate_path_with_llm", lambda *a: pytest.fail("must not generate"))
    with pytest.raises(HTTPException):
        LearningPathService(public_db).generate_path(LearningPathRequest(
            user_id=1, subject="数学", knowledge_point="方程", daily_minutes=30))
    assert public_db.query(LearningPath).count() == 0


def test_rejected_review_revises_once_then_stops(public_db, monkeypatch):
    monkeypatch.setattr(plan_knowledge, "plan_preflight", lambda *a: {"ready": False, "reason": "POINT_MISSING"})
    calls = []
    def generate(template, data, **kwargs):
        calls.append(data)
        return "实质知识正文" * 100
    monkeypatch.setattr(public, "_invoke_public_model", generate)
    monkeypatch.setattr(bootstrap, "promote_draft_to_knowledge_base", lambda *a, **k: {
        "ok": False, "reason": "MODEL_REVIEW_REJECTED", "review": {"issues": ["案例错误"]}})
    with pytest.raises(HTTPException) as error:
        public.ensure_public_knowledge(public_db, 1, "数学", "方程", allow_web=False)
    assert error.value.status_code == 422
    assert len(calls) == 2 and calls[1]["revision_issues"] == ["案例错误"]
    assert public_db.query(SystemSubject).count() == 0


def test_existing_publication_does_not_call_model(public_db, monkeypatch):
    monkeypatch.setattr(plan_knowledge, "plan_preflight", lambda *a: {"ready": True, "usable_chunks": ["public"]})
    monkeypatch.setattr(public, "_invoke_public_model", lambda *a, **k: pytest.fail("unexpected model call"))
    assert public.ensure_public_knowledge(public_db, 1, "数学", "方程")["mode"] == "public"


def test_index_failure_does_not_regenerate(public_db, monkeypatch):
    monkeypatch.setattr(plan_knowledge, "plan_preflight", lambda *a: {"ready": False, "reason": "INDEX_UNAVAILABLE"})
    monkeypatch.setattr(public, "_invoke_public_model", lambda *a, **k: pytest.fail("unexpected model call"))
    with pytest.raises(HTTPException) as error:
        public.ensure_public_knowledge(public_db, 1, "数学", "方程")
    assert error.value.status_code == 503


@pytest.mark.parametrize("evidence", ["{}", '{"type":"public_model_review","review":{"passed":true,"method":"rule"}}'])
def test_auto_approval_status_cannot_bypass_model_evidence(evidence):
    from types import SimpleNamespace

    from services.agent_service.app.services.knowledge_candidates import (
        KnowledgeCandidateConflict,
        _publish_candidate,
    )
    candidate = SimpleNamespace(status="AUTO_APPROVED", review_notes=evidence)
    with pytest.raises(KnowledgeCandidateConflict, match="model PASS"):
        _publish_candidate(None, candidate, publisher_user_id=1, lock_token="test")
