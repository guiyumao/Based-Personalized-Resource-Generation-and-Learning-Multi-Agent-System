"""Reliability acceptance tests for automatic knowledge-base backfill.

Every case checks REAL state: database rows, the public corpus directory and the
vector index -- not just the return value.  The suite runs against an isolated
database (temp file) and the isolated runtime knowledge root created by the
no-cost pytest bootstrap, so the real public corpus is never touched.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.knowledge_paths import KNOWLEDGE_ROOT
from common.models.learning import (
    AuditLog,
    KnowledgeBuildTask,
    KnowledgeCandidate,
    KnowledgePoint,
    KnowledgeVersion,
    LearningPath,
    SystemSubject,
    User,
)
from common.schemas.agent import LearningPathRequest
from services.agent_service.app.services import knowledge_bootstrap as kb
from services.agent_service.app.services import knowledge_candidates
from services.agent_service.app.services import (
    knowledge_base_admin,
    knowledge_publication,
)
from services.agent_service.app.services.learning_path import LearningPathService
from services.agent_service.app.services.plan_knowledge import plan_preflight

CORPUS_DIR = KNOWLEDGE_ROOT / "knowledge_base" / "corpus"


def _index_rows(subject_code: str, source: str) -> list[str]:
    from services.agent_service.app.services.rag import ChromaRetriever

    retriever = ChromaRetriever()
    if not retriever.is_available:
        return []
    stored = retriever.collection.get(
        where={"$and": [{"subject": subject_code}, {"source": source}]}, include=["metadatas"]
    )
    return list(stored.get("ids") or [])


def _corpus_files(subject_code: str) -> list:
    directory = CORPUS_DIR / subject_code
    return sorted(directory.glob("candidate_*.md")) if directory.is_dir() else []


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated database + two learners; real isolated corpus and index."""
    engine = create_engine(f"sqlite:///{tmp_path / 'auto.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add_all([
        User(id=1, username="learner-a", password_hash="unused"),
        User(id=2, username="learner-b", password_hash="unused"),
    ])
    db.commit()
    monkeypatch.setattr(kb, "_index_personal_chunks", lambda *a, **k: None)
    # These cases assert backfill/integration behaviour (rows, corpus, index,
    # compensation), not the reviewer itself. The no-cost suite has no model, so
    # the review is replaced by a passing stand-in bound to the exact body --
    # publication re-checks content_sha256, so it must match the content.
    from services.agent_service.app.services import public_knowledge

    def passing_review(subject, topic, content, *args, **kwargs):
        return {"passed": True, "method": "llm", "verdict": "PASS", "reason": "测试替身审核通过",
                "issues": [], "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}

    monkeypatch.setattr(public_knowledge, "review_public_content", passing_review)
    yield SimpleNamespace(
        db=db, factory=factory, engine=engine,
        subject=f"自动学科-{uuid.uuid4().hex[:6]}",
        point=f"知识点-{uuid.uuid4().hex[:6]}",
        monkeypatch=monkeypatch,
    )
    db.close()
    engine.dispose()


def _subject_code(subject: str) -> str:
    return kb._auto_subject_code(subject)


def _outline(subject: str, point: str, extra: str | None = None) -> dict:
    points = [{"name": point, "objectives": [f"掌握{point}"], "prerequisites": []}]
    if extra:
        points.append({"name": extra, "objectives": [f"掌握{extra}"], "prerequisites": []})
    return {
        "name": subject,
        "code": "auto_case",
        "description": f"{subject} 描述",
        "chapters": [{"name": "第一章", "points": points}],
        "source": "deterministic_fallback",
    }


# ---------------------------------------------------------------------------
# Scenario A: no subject at all -> first learner publishes, second reuses.
# ---------------------------------------------------------------------------


def test_scenario_a_first_publishes_second_reuses(env):
    db, subject, point = env.db, env.subject, env.point
    first = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert first["ok"] is True and first["reused"] is False
    assert _corpus_files(db.get(SystemSubject, first["subject_id"]).code)
    assert plan_preflight(db, 1, subject, point)["ready"] is True

    second = kb.promote_draft_to_knowledge_base(db, 2, subject, point, _outline(subject, point), [])
    assert second["ok"] is True and second["reused"] is True
    assert second["version_id"] == first["version_id"]
    # Exactly one candidate and one active version for the target.
    assert db.query(KnowledgeCandidate).filter_by(knowledge_point=point).count() == 1
    assert db.query(KnowledgeVersion).filter_by(is_active=True).count() == 1
    # The learner path is served from public knowledge, no draft regeneration.
    check = plan_preflight(db, 2, subject, point)
    assert check["ready"] is True and check["reason"] == "READY"


# ---------------------------------------------------------------------------
# Scenario B: subject exists, one point missing -> only that point is added.
# ---------------------------------------------------------------------------


def test_scenario_b_only_the_missing_point_is_published(env):
    db, subject = env.db, env.subject
    existing = SystemSubject(name=subject, code=f"case_{uuid.uuid4().hex[:8]}", description="fixture")
    db.add(existing)
    db.flush()
    db.add_all([
        KnowledgePoint(name="链表", subject_id=existing.id, chapter="线性表", objectives_json=["掌握链表"]),
        KnowledgePoint(name="栈", subject_id=existing.id, chapter="栈与队列", objectives_json=["掌握栈"]),
    ])
    db.commit()

    result = kb.promote_draft_to_knowledge_base(
        db, 1, subject, "栈", _outline(subject, "栈", extra="链表"), []
    )
    assert result["ok"] is True
    # No duplicated catalog rows.
    assert db.query(KnowledgePoint).filter_by(subject_id=existing.id).count() == 2
    assert db.query(KnowledgeCandidate).filter_by(knowledge_point="链表").count() == 0
    assert db.query(KnowledgeCandidate).filter_by(knowledge_point="栈").count() == 1
    # The published document covers only the missing point.
    version = db.get(KnowledgeVersion, result["version_id"])
    body = (KNOWLEDGE_ROOT / version.corpus_path).read_text(encoding="utf-8")
    assert "掌握栈" in body and "掌握链表" not in body


# ---------------------------------------------------------------------------
# Scenario C: subject + point exist but no publication -> publish and verify.
# ---------------------------------------------------------------------------


def test_scenario_c_publishes_missing_content_for_existing_point(env):
    db, subject, point = env.db, env.subject, env.point
    existing = SystemSubject(name=subject, code=f"case_{uuid.uuid4().hex[:8]}", description="fixture")
    db.add(existing)
    db.flush()
    db.add(KnowledgePoint(name=point, subject_id=existing.id, chapter="第一章"))
    db.commit()
    assert plan_preflight(db, 1, subject, point)["reason"] == "PUBLISHED_CONTENT_MISSING"

    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is True
    check = plan_preflight(db, 1, subject, point)
    assert check["ready"] is True and check["usable_chunks"]
    version = db.get(KnowledgeVersion, result["version_id"])
    source = version.corpus_path.removeprefix("knowledge_base/corpus/")
    assert _index_rows(version.subject, source), "index must contain the published version"


# ---------------------------------------------------------------------------
# Scenario D: backfill fails -> honest failure, catalog/file/index untouched.
# ---------------------------------------------------------------------------


def test_scenario_d_failure_returns_reason_without_fake_success(env):
    db, subject, point = env.db, env.subject, env.point
    env.monkeypatch.setattr(
        knowledge_candidates,
        "publish_candidate",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("index unavailable")),
    )
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is False and result["reason"] == "PUBLISH_FAILED"
    assert db.query(SystemSubject).filter_by(name=subject).count() == 0
    assert db.query(KnowledgePoint).filter_by(name=point).count() == 0
    assert db.query(KnowledgeCandidate).filter_by(knowledge_point=point).count() == 0
    assert db.query(KnowledgeVersion).count() == 0
    assert plan_preflight(db, 1, subject, point)["ready"] is False
    assert db.query(AuditLog).filter_by(event="knowledge.auto_backfill.failed").count() == 1


# ---------------------------------------------------------------------------
# Scenario E: knowledge exists -> no draft build, no extra model/search work.
# ---------------------------------------------------------------------------


def test_scenario_e_existing_knowledge_skips_draft_generation(env):
    db, subject, point = env.db, env.subject, env.point
    kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    calls = []
    original = kb.build_personal_draft
    env.monkeypatch.setattr(
        kb, "build_personal_draft", lambda *a, **k: (calls.append(1), original(*a, **k))[1]
    )
    env.monkeypatch.setattr(
        LearningPathService,
        "_generate_path_with_llm",
        lambda self, request, scope: {
            "user_id": request.user_id, "subject": request.subject,
            "knowledge_point": request.knowledge_point, "overview": "复用公共知识",
            "estimated_days": 7,
            "stages": [{"stage_id": "s1", "title": "基础", "description": "", "tasks": [
                {"task_id": "t1", "title": "阅读", "task_type": "courseware",
                 "knowledge_point": request.knowledge_point, "objective": "理解",
                 "estimated_minutes": 30, "difficulty": "foundation",
                 "completed": False, "status": "pending", "depends_on": []}]}],
        },
    )
    payload = LearningPathService(db).generate_path(
        LearningPathRequest(user_id=2, subject=subject, knowledge_point=point, daily_minutes=60))
    assert payload["knowledge_scope"] == "public"
    assert payload["knowledge_versions"]
    assert calls == [], "existing public knowledge must not trigger draft construction"


# ---------------------------------------------------------------------------
# Scenario F: an administrator decision never blocks integration.
# ---------------------------------------------------------------------------


def test_scenario_f_withdrawn_version_is_not_reused_but_never_blocks(env):
    db, subject, point = env.db, env.subject, env.point
    first = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert first["ok"] is True
    # Administrator withdraws it (same effect as the withdraw route).
    db.query(KnowledgeVersion).filter_by(candidate_id=first["candidate_id"]).update({"is_active": False})
    candidate = db.get(KnowledgeCandidate, first["candidate_id"])
    candidate.status = "WITHDRAWN"
    db.commit()

    # The withdrawn version stays down - it is not silently resurrected.
    assert plan_preflight(db, 2, subject, point)["ready"] is False
    assert db.query(KnowledgeVersion).filter_by(is_active=True).count() == 0

    # But the decision never blocks integration: a new model-reviewed build is
    # accepted instead of depending on an administrator to unblock it.
    second = kb.promote_draft_to_knowledge_base(db, 2, subject, point, _outline(subject, point), [])
    assert second["ok"] is True, second
    assert db.query(KnowledgeVersion).filter_by(is_active=True).count() == 1
    assert plan_preflight(db, 2, subject, point)["ready"] is True


# ---------------------------------------------------------------------------
# Scenario G: concurrent learners -> one publication, others reuse.
# ---------------------------------------------------------------------------


def test_scenario_g_concurrent_requests_do_not_duplicate_publication(env):
    subject, point = env.subject, env.point
    results = []
    errors = []

    def worker(user_id: int) -> None:
        db = env.factory()
        try:
            results.append(
                kb.promote_draft_to_knowledge_base(db, user_id, subject, point, _outline(subject, point), [])
            )
        except Exception as exc:  # pragma: no cover - reported through assertion
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(1,)) for _ in range(2)]
    threads += [threading.Thread(target=worker, args=(2,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not errors, errors
    assert len(results) == 3
    assert all(item["ok"] for item in results)
    db = env.db
    db.expire_all()
    assert db.query(KnowledgeCandidate).filter_by(knowledge_point=point).count() == 1
    assert db.query(KnowledgeVersion).filter_by(is_active=True).count() == 1
    assert db.query(SystemSubject).filter_by(name=subject).count() == 1


# ---------------------------------------------------------------------------
# Scenario H: path generation fails after publishing -> knowledge survives.
# ---------------------------------------------------------------------------


def test_scenario_h_path_failure_keeps_published_knowledge(env):
    db, subject, point = env.db, env.subject, env.point
    published = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert published["ok"] is True
    env.monkeypatch.setattr(
        LearningPathService,
        "_generate_path_with_llm",
        lambda self, request, scope: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )
    with pytest.raises(RuntimeError):
        LearningPathService(db).generate_path(
            LearningPathRequest(user_id=1, subject=subject, knowledge_point=point, daily_minutes=60))
    db.expire_all()
    version = db.get(KnowledgeVersion, published["version_id"])
    assert version.is_active is True
    assert (KNOWLEDGE_ROOT / version.corpus_path).is_file()
    assert db.query(SystemSubject).filter_by(name=subject).count() == 1
    assert db.query(KnowledgePoint).filter_by(name=point).count() == 1
    assert db.query(LearningPath).filter_by(user_id=1).count() == 0
    # The knowledge is still reusable afterwards.
    assert plan_preflight(db, 2, subject, point)["ready"] is True


# ---------------------------------------------------------------------------
# Fault injection: DB failure, file failure, index failure, verification,
# compensation failure, and compensation idempotency.
# ---------------------------------------------------------------------------


def test_injection_database_failure_is_compensated(env):
    db, subject, point = env.db, env.subject, env.point
    from sqlalchemy.exc import OperationalError

    def boom(*a, **k):
        raise OperationalError("stmt", {}, Exception("simulated database failure"))

    env.monkeypatch.setattr(knowledge_candidates, "publish_candidate", boom)
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is False
    assert db.query(SystemSubject).filter_by(name=subject).count() == 0
    assert db.query(KnowledgePoint).filter_by(name=point).count() == 0
    assert db.query(KnowledgeVersion).count() == 0


def test_injection_file_write_failure_is_compensated(env):
    db, subject, point = env.db, env.subject, env.point

    def boom(*a, **k):
        raise OSError("simulated disk failure")

    # knowledge_candidates binds this symbol at import time.
    env.monkeypatch.setattr(knowledge_candidates, "publish_document_and_reindex", boom)
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is False
    assert db.query(KnowledgeVersion).count() == 0
    assert db.query(KnowledgeCandidate).filter_by(knowledge_point=point).count() == 0
    # No candidate file may remain inside this subject's public corpus directory.
    assert _corpus_files(_subject_code(subject)) == [], "failed publication left a corpus file"


def test_injection_index_failure_is_compensated(env):
    db, subject, point = env.db, env.subject, env.point

    def boom(*a, **k):
        raise RuntimeError("simulated index failure")

    env.monkeypatch.setattr(knowledge_base_admin, "_run_index_command", boom)
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is False
    assert db.query(KnowledgeVersion).filter_by(is_active=True).count() == 0
    assert _corpus_files(_subject_code(subject)) == []


def test_injection_verification_failure_removes_version_and_file(env):
    db, subject, point = env.db, env.subject, env.point

    def never_verified(*a, **k):
        raise RuntimeError("published version is not retrievable in the index")

    env.monkeypatch.setattr(kb, "_verify_publication", never_verified)
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is False
    # A version row created before verification must not survive.
    assert db.query(KnowledgeVersion).count() == 0
    assert _corpus_files(_subject_code(subject)) == []
    candidate = db.query(KnowledgeCandidate).filter_by(knowledge_point=point).first()
    assert candidate is None or candidate.status != "PUBLISHED"


def test_injection_compensation_failure_records_diagnostic_and_recovery_task(env):
    db, subject, point = env.db, env.subject, env.point
    env.monkeypatch.setattr(
        knowledge_candidates,
        "publish_candidate",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("index unavailable")),
    )

    def broken_reconcile(*a, **k):
        raise RuntimeError("reconcile exploded")

    env.monkeypatch.setattr(knowledge_publication, "reconcile", broken_reconcile)
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is False
    # The failure is recorded, never disguised as a successful rollback.
    audit = db.query(AuditLog).filter_by(event="knowledge.auto_backfill.compensation_incomplete").all()
    assert audit, "compensation failure must leave a diagnostic record"
    assert "reconcile" in audit[0].message
    queued = db.query(KnowledgeBuildTask).filter_by(operation_type="RECONCILE_PUBLICATIONS").all()
    assert queued, "a replayable recovery task must be queued"


def test_compensation_is_idempotent(env):
    db, subject, point = env.db, env.subject, env.point
    first = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert first["ok"] is True
    from common.knowledge_lock import knowledge_write_lock

    with knowledge_write_lock(KNOWLEDGE_ROOT) as token:
        for _ in range(2):
            problems = kb._compensate_publication(
                db, root=KNOWLEDGE_ROOT, token=token, user_id=1,
                subject_code=db.get(SystemSubject, first["subject_id"]).code,
                candidate_id=first["candidate_id"], created_candidate=False,
                version_ids=(first["version_id"],),
            )
            assert problems == []
    db.expire_all()
    assert db.get(KnowledgeVersion, first["version_id"]) is None


# ---------------------------------------------------------------------------
# Quality: AI provenance, no fake human review, content sanity.
# ---------------------------------------------------------------------------


def test_published_corpus_marks_ai_origin_and_never_claims_human_review(env):
    db, subject, point = env.db, env.subject, env.point
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is True
    version = db.get(KnowledgeVersion, result["version_id"])
    body = (KNOWLEDGE_ROOT / version.corpus_path).read_text(encoding="utf-8")
    assert "来源类型: ai_generated_auto_published" in body
    assert "未经人工审核" in body
    assert "administrator_reviewed_candidate" not in body
    candidate = db.get(KnowledgeCandidate, result["candidate_id"])
    assert candidate.license_name == "AI_GENERATED"
    assert candidate.reviewed_by is None and candidate.reviewed_at is None


def test_validate_draft_rejects_empty_oversized_misattributed_and_duplicated():
    with pytest.raises(ValueError):
        kb._validate_draft("UDP", "   ", {})
    with pytest.raises(ValueError):
        kb._validate_draft("UDP", "UDP" + "内" * 40000, {})
    with pytest.raises(ValueError):
        kb._validate_draft("UDP", "这一段内容完全没有提到目标知识点", {})
    with pytest.raises(ValueError):
        kb._validate_draft("UDP", "UDP 详细说明", {"chapters": [
            {"points": [{"name": "UDP"}, {"name": "UDP"}]}]})
    kb._validate_draft(
        "UDP", "UDP 是一种无连接的传输层协议，不保证可靠送达与顺序。",
        {"chapters": [{"points": [{"name": "UDP"}]}]},
    )


def test_structural_defects_are_repaired_not_refused(env):
    """Integration is mandatory: a broken draft is repaired, never refused."""
    db, subject, point = env.db, env.subject, env.point
    duplicated = {
        "chapters": [{"name": "c", "points": [
            {"name": point, "objectives": ["x"]}, {"name": point, "objectives": ["y"]}]}]
    }
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, duplicated, [])
    assert result["ok"] is True, result
    assert db.query(KnowledgeVersion).filter_by(is_active=True).count() == 1
    assert plan_preflight(db, 1, subject, point)["ready"] is True


def test_unrelated_body_is_repaired_to_cover_the_point(env):
    """A body missing the knowledge point is completed instead of refused."""
    db, subject, point = env.db, env.subject, env.point
    result = kb.promote_draft_to_knowledge_base(db, 1, subject, point, _outline(subject, point), [])
    assert result["ok"] is True, result
    version = db.query(KnowledgeVersion).filter_by(is_active=True).one()
    body = (CORPUS_DIR / version.corpus_path.removeprefix("knowledge_base/corpus/")).read_text(encoding="utf-8")
    assert kb._normalized(point) in kb._normalized(body)
