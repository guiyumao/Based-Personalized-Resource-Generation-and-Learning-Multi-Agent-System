"""P0-2: student-triggered personal subject draft (outline + chunks, no public leak)."""
from copy import deepcopy

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.models.learning import KnowledgeBuildTask, LearningPath, SystemSubject, User
from common.schemas.agent import LearningPathRequest
from services.agent_service.app.services.knowledge_bootstrap import build_personal_draft
from services.agent_service.app.services.learning_path import LearningPathService


@pytest.fixture
def boot_db(monkeypatch):
    # Never touch a real Chroma collection from unit tests.
    from services.agent_service.app.services import knowledge_bootstrap
    monkeypatch.setattr(knowledge_bootstrap, "_index_personal_chunks", lambda *a, **k: None)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=1, username="learner", password_hash="unused"))
        db.commit()
        yield db
    engine.dispose()


def test_build_personal_draft_is_personal_and_reusable(boot_db):
    db = boot_db
    before_subjects = db.query(SystemSubject).count()

    first = build_personal_draft(db, 1, "数据结构", "链表")
    assert first["reused"] is False
    assert first["outline"]["name"] == "数据结构"
    assert first["outline"]["source"] == "deterministic_fallback"
    assert first["chunks"], "personal outline must produce retrieval chunks"
    assert all(c["metadata"]["scope"] == "personal_draft" for c in first["chunks"])
    assert first["chunks"][0]["metadata"]["source"] == "personal_draft"

    # Personal draft must never add to the public catalog.
    assert db.query(SystemSubject).count() == before_subjects

    task = db.query(KnowledgeBuildTask).filter_by(actor_user_id=1, subject="数据结构").one()
    assert task.operation_type == "PERSONAL_SUBJECT_DRAFT"
    assert task.trigger_source == "student"
    assert task.status == "COMPLETED"
    assert task.result_json["scope"] == "personal_draft"

    # Same learner reuses the draft (no second task).
    second = build_personal_draft(db, 1, "数据结构", "链表")
    assert second["reused"] is True
    assert second["task_id"] == task.id
    assert db.query(KnowledgeBuildTask).filter_by(actor_user_id=1, subject="数据结构").count() == 1


def test_personal_draft_is_isolated_per_learner(boot_db):
    db = boot_db
    db.add(User(id=2, username="other", password_hash="unused"))
    db.commit()
    build_personal_draft(db, 1, "数据结构", "链表")
    other = build_personal_draft(db, 2, "数据结构", "链表")
    assert other["reused"] is False
    assert db.query(KnowledgeBuildTask).filter_by(subject="数据结构").count() == 2
    # each learner only sees their own task under their own actor id
    assert db.query(KnowledgeBuildTask).filter_by(subject="数据结构", actor_user_id=1).count() == 1


def test_visible_chunks_drops_personal_draft_rows():
    from services.agent_service.app.services.knowledge_publication import visible_chunks
    rows = [
        {"id": "pub", "metadata": {"source": "docs/pub.md"}},
        {"id": "personal", "metadata": {"source": "personal_draft", "scope": "personal_draft"}},
    ]
    assert [row["id"] for row in visible_chunks(rows)] == ["pub"]


def test_retrieve_personal_scopes_to_owner_and_scope():
    from services.agent_service.app.services.rag import ChromaRetriever
    captured = {}

    def fake_unchecked(query, top_k=None, **kwargs):
        captured.update(kwargs)
        return [{"id": "x", "content": "c",
                 "metadata": {"scope": "personal_draft", "owner_user_id": "7"}}]

    retriever = ChromaRetriever.__new__(ChromaRetriever)  # bypass __init__ (no Chroma)
    retriever._retrieve_with_metadata_unchecked = fake_unchecked
    rows = retriever.retrieve_personal(7, "链表", subject="数据结构")
    assert rows
    assert captured["filters"] == {"owner_user_id": "7", "scope": "personal_draft", "subject": "数据结构"}
    assert captured["cache_scope"] == "private"
    assert captured["user_id"] == 7


def test_generate_path_uses_personal_outline_when_subject_missing(boot_db, monkeypatch):
    db = boot_db
    captured = {}

    def fake_generate(self, request, teacher_scope):
        captured["retrieval_context"] = deepcopy(request.retrieval_context)
        return {
            "user_id": request.user_id, "subject": request.subject,
            "knowledge_point": request.knowledge_point, "overview": "从零学习",
            "estimated_days": 42,
            "stages": [{"stage_id": "s1", "title": "基础", "description": "", "tasks": [
                {"task_id": "t1", "title": "入门", "task_type": "courseware",
                 "knowledge_point": request.knowledge_point, "objective": "理解",
                 "estimated_minutes": 30, "difficulty": "foundation", "completed": False,
                 "status": "pending", "depends_on": []}]}],
        }

    monkeypatch.setattr(LearningPathService, "_generate_path_with_llm", fake_generate)
    payload = LearningPathService(db).generate_path(
        LearningPathRequest(user_id=1, subject="数据结构", knowledge_point="链表", daily_minutes=60))

    assert payload["knowledge_scope"] == "personal_draft"
    assert payload["knowledge_draft"]["name"] == "数据结构"
    assert payload["knowledge_draft_task_id"] is not None
    assert payload.get("subject_id") is None
    assert "knowledge_versions" not in payload
    # The LLM prompt must be grounded on the personal outline chunks.
    chunks = captured["retrieval_context"]["retrieved_chunks"]
    assert chunks and all(c["metadata"]["scope"] == "personal_draft" for c in chunks)
    assert captured["retrieval_context"]["personal_outline"]["name"] == "数据结构"
    # Persisted path keeps the draft trace and is not public.
    saved = db.query(LearningPath).filter_by(user_id=1, status="active").one()
    assert saved.path_data_json["knowledge_scope"] == "personal_draft"
    assert saved.path_data_json["knowledge_draft"]["name"] == "数据结构"
