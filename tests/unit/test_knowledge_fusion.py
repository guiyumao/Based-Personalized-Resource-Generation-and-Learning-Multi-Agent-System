"""Deterministic knowledge filter/classify/fusion decisions (no model calls)."""
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.models.learning import (
    KnowledgeBuildTask,
    KnowledgeCandidate,
    KnowledgePoint,
    KnowledgeVersion,
    SystemSubject,
    User,
)
from services.agent_service.app.services import knowledge_fusion


@pytest.fixture
def fusion_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=1, username="admin", password_hash="unused"))
        db.add(SystemSubject(id=10, name="数据结构", code="data_structures", description=""))
        db.flush()
        db.add_all([
            KnowledgePoint(id=101, name="链表", subject_id=10, chapter="线性表"),
            KnowledgePoint(id=102, name="栈", subject_id=10, chapter="栈与队列"),
        ])
        db.commit()
        yield db
    engine.dispose()


def _make_candidate(db, *, point="链表", content="x" * 300,
                    source="https://example.com/a", status="DRAFT"):
    task = KnowledgeBuildTask(
        actor_user_id=1, client_request_id=f"t-{uuid4().hex[:8]}",
        request_hash="f" * 64, trigger_source="manual",
        operation_type="FETCH_SOURCE", subject="data_structures",
    )
    db.add(task)
    db.flush()
    candidate = KnowledgeCandidate(
        creator_user_id=1, source_task_id=task.id,
        subject="data_structures", knowledge_point=point, title="t", content=content,
        source_url=source, source_hash=hashlib.sha256(source.encode()).hexdigest(),
        content_hash=hashlib.sha256(content.encode()).hexdigest(), status=status,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def test_classify_matches_subject_and_point(fusion_db):
    db = fusion_db
    candidate = _make_candidate(db)
    result = knowledge_fusion.classify_candidate(db, candidate)
    assert result["subject_id"] == 10
    assert result["point_id"] == 101
    assert result["complete"] is True


def test_quality_blocks_short_and_untraceable(fusion_db):
    db = fusion_db
    candidate = _make_candidate(db, content="short", source="")
    result = knowledge_fusion.assess_quality(candidate)
    assert result.passed is False
    assert "CONTENT_TOO_SHORT" in result.reasons
    assert "SOURCE_NOT_TRACEABLE" in result.reasons


def test_decision_sequence_create_duplicate_supplement_revise(fusion_db):
    db = fusion_db
    candidate = _make_candidate(db)
    assert knowledge_fusion.decide_fusion(db, candidate)["action"] == "create_version"

    db.add(KnowledgeVersion(
        candidate_id=candidate.id, version_number=1, subject="data_structures",
        knowledge_point="链表", title="t", content=candidate.content,
        source_url=candidate.source_url, content_hash=candidate.content_hash,
        corpus_path="knowledge_base/corpus/data_structures/x.md", published_by=1, is_active=True,
    ))
    db.commit()
    # identical content -> duplicate
    same = _make_candidate(db)
    same.content_hash = hashlib.sha256(b"y" * 300).hexdigest()
    db.commit()
    assert knowledge_fusion.decide_fusion(db, candidate)["action"] == "duplicate"

    # existing richer (300 chars) vs shorter candidate -> supplement
    shorter = _make_candidate(db, content="z" * 10)
    assert knowledge_fusion.decide_fusion(db, shorter)["action"] == "supplement"

    # candidate larger than existing -> revise
    larger = _make_candidate(db, content="w" * 900)
    assert knowledge_fusion.decide_fusion(db, larger)["action"] == "revise"


def test_auto_publish_policy(fusion_db):
    db = fusion_db
    candidate = _make_candidate(db)
    manual = knowledge_fusion.evaluate_candidate(db, candidate, policy="manual")
    assert manual["auto_publish"] is False
    assert manual["auto_publish_reason"] == "POLICY_MANUAL"

    strict = knowledge_fusion.evaluate_candidate(db, candidate, policy="strict_auto")
    assert strict["auto_publish"] is True
    assert strict["auto_publish_reason"] == "AUTO_PUBLISH_OK"

    # A revise action always needs human review, even in strict_auto.
    db.add(KnowledgeVersion(
        candidate_id=candidate.id, version_number=1, subject="data_structures",
        knowledge_point="链表", title="t", content="short", source_url=candidate.source_url,
        content_hash=hashlib.sha256(b"short").hexdigest(),
        corpus_path="knowledge_base/corpus/data_structures/y.md", published_by=1, is_active=True,
    ))
    db.commit()
    larger = _make_candidate(db, content="v" * 900)
    revoked = knowledge_fusion.evaluate_candidate(db, larger, policy="strict_auto")
    assert revoked["auto_publish"] is False
    assert revoked["auto_publish_reason"] == "ACTION_REQUIRES_REVIEW:revise"


def test_fusion_summary_counts(fusion_db):
    db = fusion_db
    _make_candidate(db)
    _make_candidate(db, content="short", source="")
    summary = knowledge_fusion.fusion_summary(db)
    assert summary["candidates"] == 2
    assert summary["blocked"] >= 1
    assert summary["published"] == 0
