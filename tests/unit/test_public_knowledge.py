"""Fail-closed model review, no private fallback, and shared retrieval contracts."""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from common.db.base import Base
from common.models.learning import LearningPath, SystemSubject, User
from common.schemas.agent import LearningPathRequest
from services.agent_service.app.services import knowledge_bootstrap as bootstrap
from services.agent_service.app.services import plan_knowledge
from services.agent_service.app.services import public_knowledge as public
from services.agent_service.app.services.learning_path import LearningPathService


@pytest.fixture
def public_db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    from services.agent_service.app.services import knowledge_tasks
    monkeypatch.setattr(knowledge_tasks, "SessionLocal", sessionmaker(bind=engine))
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


def test_rejected_review_is_persisted_and_automatically_revised(public_db, monkeypatch):
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
    assert error.value.status_code == 202
    from common.models.learning import KnowledgeBuildTask
    task = public_db.get(KnowledgeBuildTask, error.value.detail["task_id"])
    assert task.status == "QUEUED"
    assert task.result_json["public_body"]
    assert task.result_json["revision_issues"] == ["案例错误"]
    assert len(calls) == 1
    from datetime import datetime, timedelta

    from services.agent_service.app.services import knowledge_tasks
    task.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
    public_db.commit()
    knowledge_tasks.execute_task(task.id)
    public_db.expire_all()
    assert calls[1]["revision_issues"] == ["案例错误"]
    assert calls[1]["previous_content"].startswith("实质知识正文")
    assert public_db.get(KnowledgeBuildTask, task.id).status == "QUEUED"


def test_existing_publication_does_not_call_model(public_db, monkeypatch):
    monkeypatch.setattr(plan_knowledge, "plan_preflight", lambda *a: {"ready": True, "usable_chunks": ["public"]})
    monkeypatch.setattr(public, "_invoke_public_model", lambda *a, **k: pytest.fail("unexpected model call"))
    assert public.ensure_public_knowledge(public_db, 1, "数学", "方程")["mode"] == "public"


def test_index_failure_does_not_regenerate(public_db, monkeypatch):
    monkeypatch.setattr(plan_knowledge, "plan_preflight", lambda *a: {"ready": False, "reason": "INDEX_UNAVAILABLE"})
    monkeypatch.setattr(public, "_invoke_public_model", lambda *a, **k: pytest.fail("unexpected model call"))
    with pytest.raises(HTTPException) as error:
        public.ensure_public_knowledge(public_db, 1, "数学", "方程")
    assert error.value.status_code == 202


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


def test_model_modifies_then_publishes_without_administrator(public_db, monkeypatch):
    from datetime import datetime, timedelta

    from common.models.learning import KnowledgeBuildTask, KnowledgeCandidate
    from services.agent_service.app.services import knowledge_tasks
    calls = []
    def invoke(template, data, **kwargs):
        calls.append((template, data))
        reviews = sum(name == "public_knowledge_review.md" for name, _ in calls)
        if template == "public_knowledge_review.md":
            return json.dumps({"verdict": "REJECT" if reviews == 1 else "PASS",
                               "reason": "修订案例" if reviews == 1 else "修订后核验通过",
                               "issues": ["修正案例计算"] if reviews == 1 else []})
        return "方程验算：定义、原理、案例、中间过程与边界。" * 50
    monkeypatch.setattr(public, "_invoke_public_model", invoke)
    with pytest.raises(HTTPException) as response:
        public.ensure_public_knowledge(public_db, 1, "修订融合测试", "方程验算", allow_web=False)
    assert response.value.status_code == 202
    task = public_db.get(KnowledgeBuildTask, response.value.detail["task_id"])
    assert task.status == "QUEUED" and task.result_json["public_body"]
    assert task.completed_at is None
    task.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
    public_db.commit()
    knowledge_tasks.execute_task(task.id)
    public_db.expire_all()
    assert public_db.get(KnowledgeBuildTask, task.id).status == "COMPLETED"
    result = public.ensure_public_knowledge(public_db, 1, "修订融合测试", "方程验算", allow_web=False)
    assert result["mode"] == "public" and result["published_versions"]
    candidate = public_db.query(KnowledgeCandidate).filter_by(knowledge_point="方程验算").one()
    assert candidate.status == "PUBLISHED" and candidate.reviewed_by is None
    assert calls[2][1]["revision_issues"] == ["修正案例计算"]
    assert calls[2][1]["previous_content"]
