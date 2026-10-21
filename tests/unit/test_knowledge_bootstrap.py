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


def test_ssrf_allows_fake_ip_only_when_explicitly_enabled(monkeypatch):
    import services.agent_service.app.services.deepseek_search as ds
    monkeypatch.delenv("DEEPSEEK_SEARCH_ALLOW_FAKE_IP", raising=False)
    # localhost resolves to 127.0.0.1 which is not a global IP -> rejected by default
    assert ds._resolve_public_host("localhost") is False
    monkeypatch.setenv("DEEPSEEK_SEARCH_ALLOW_FAKE_IP", "1")
    assert ds._resolve_public_host("localhost") is True


def test_search_and_fetch_is_guarded_when_not_authorized(monkeypatch):
    import services.agent_service.app.services.deepseek_search as ds
    from services.agent_service.app.services import knowledge_bootstrap as kb
    monkeypatch.delenv("RUN_LIVE_LLM", raising=False)
    monkeypatch.delenv("DEEPSEEK_LIVE_PAID_ACK", raising=False)
    called = []
    monkeypatch.setattr(ds, "search_sources", lambda *a, **k: called.append("search") or [])
    assert kb._search_and_fetch_personal(object(), 1, "数据结构", "链表") is None
    assert called == []


def test_search_and_fetch_uses_inline_content_when_authorized(boot_db, monkeypatch):
    import services.agent_service.app.services.deepseek_search as ds
    from services.agent_service.app.services import knowledge_bootstrap as kb
    db = boot_db
    monkeypatch.setenv("RUN_LIVE_LLM", "1")
    monkeypatch.setenv("DEEPSEEK_LIVE_PAID_ACK", "1")
    monkeypatch.setattr(ds, "search_sources", lambda query, count=5, need_content=False: [
        {"title": "t", "url": "https://example.com/a", "summary": "s", "content": "x" * 40},
    ])
    out = kb._search_and_fetch_personal(db, 1, "数据结构", "链表")
    assert out is not None
    assert out["chunk"]["content"] == "x" * 40
    task = db.query(KnowledgeBuildTask).filter_by(
        actor_user_id=1, operation_type="FETCH_SOURCE").one()
    assert task.status == "COMPLETED"
    assert task.result_json["source"]["content"] == "x" * 40


def test_build_personal_draft_includes_enriched_source(boot_db, monkeypatch):
    from services.agent_service.app.services import knowledge_bootstrap as kb
    db = boot_db
    monkeypatch.setattr(kb, "_search_and_fetch_personal", lambda *a, **k: {
        "candidate_id": 9,
        "source": {"url": "https://example.com/a", "title": "t"},
        "chunk": {"content": "real fetched content",
                  "metadata": {"source": "https://example.com/a", "scope": "personal_draft"}},
    })
    draft = kb.build_personal_draft(db, 1, "数据结构", "链表")
    assert draft["sources"][0]["url"] == "https://example.com/a"
    assert any(c["content"] == "real fetched content" for c in draft["chunks"])
    task = db.query(KnowledgeBuildTask).filter_by(actor_user_id=1, subject="数据结构").one()
    assert task.result_json["candidate_id"] == 9


def test_generate_path_backfills_knowledge_base_when_subject_missing(boot_db, monkeypatch):
    """The generated draft is published into the knowledge base immediately.

    After generation the subject/point exist in the catalog with a published,
    retrievable version, so the NEXT request is served from the knowledge base
    instead of regenerating a draft.
    """
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

    # The draft was promoted: this very plan already runs in public mode.
    assert payload["knowledge_scope"] == "public"
    assert payload["subject_id"] is not None
    assert payload["knowledge_versions"]
    assert "knowledge_draft" not in payload
    # The LLM prompt is grounded on the freshly published public chunks.
    chunks = captured["retrieval_context"]["retrieved_chunks"]
    assert chunks and all(c["metadata"].get("scope") != "personal_draft" for c in chunks)
    # Catalog + publication records exist.
    from common.models.learning import KnowledgeCandidate, KnowledgePoint, KnowledgeVersion

    subject = db.query(SystemSubject).filter_by(name="数据结构").one()
    point = db.query(KnowledgePoint).filter_by(subject_id=subject.id, name="链表").one()
    candidate = db.query(KnowledgeCandidate).filter_by(subject=subject.code, knowledge_point="链表").one()
    assert candidate.status == "PUBLISHED"
    assert candidate.license_name == "AI_GENERATED"
    version = db.get(KnowledgeVersion, candidate.published_version_id)
    assert version is not None and version.is_active
    assert point.construction_status == "PUBLISHED"
    # Persisted path references the public catalog.
    saved = db.query(LearningPath).filter_by(user_id=1, status="active").one()
    assert saved.path_data_json["knowledge_scope"] == "public"
    assert saved.path_data_json["subject_id"] == subject.id
    # The NEXT request hits the knowledge base directly without regeneration.
    from services.agent_service.app.services.plan_knowledge import plan_preflight

    assert plan_preflight(db, 1, "数据结构", "链表")["ready"] is True


def test_generate_path_backfills_publication_when_subject_exists(tmp_path, monkeypatch):
    from common.models.learning import KnowledgePoint, SystemSubject
    engine = create_engine(
        f"sqlite:///{tmp_path / 'real.sqlite'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=1, username="learner", password_hash="unused"))
        db.add(SystemSubject(id=10, name="数据结构", code="data_structures", description="fixture"))
        db.flush()
        db.add_all([
            KnowledgePoint(id=101, name="链表", subject_id=10, chapter="线性表"),
            KnowledgePoint(id=102, name="栈", subject_id=10, chapter="栈与队列"),
        ])
        db.commit()
        monkeypatch.setattr(LearningPathService, "_generate_path_with_llm",
                            lambda self, request, scope: {
            "user_id": request.user_id, "subject": request.subject,
            "knowledge_point": request.knowledge_point, "overview": "fixture",
            "estimated_days": 7,
            "stages": [{"stage_id": "s1", "title": "基础", "description": "", "tasks": [
                {"task_id": "t1", "title": "学习链表", "task_type": "courseware",
                 "knowledge_point": "链表基础", "objective": "理解", "estimated_minutes": 30,
                 "difficulty": "foundation", "completed": False, "status": "pending",
                 "depends_on": []},
            ]}],
        })
        payload = LearningPathService(db).generate_path(
            LearningPathRequest(user_id=1, subject="数据结构", knowledge_point="链表", daily_minutes=60))
        # The real curriculum was missing published content; the generated draft
        # is published into the knowledge base, so the plan runs in public mode.
        assert payload["knowledge_scope"] == "public"
        assert payload["subject_id"] == 10
        task = payload["stages"][0]["tasks"][0]
        assert task["knowledge_point"] == "链表"  # snapped from the LLM sub-topic
        assert task["knowledge_point_id"] == 101
        from services.agent_service.app.services.plan_knowledge import plan_preflight

        assert plan_preflight(db, 1, "数据结构", "链表")["ready"] is True
    engine.dispose()


def test_promote_draft_rolls_back_when_publication_fails(boot_db, monkeypatch):
    """A failed backfill must not pollute the public catalog.

    When the retrieval index cannot verify the publication the learner keeps the
    personal draft and the shared catalog is left exactly as it was.
    """
    from services.agent_service.app.services import (
        knowledge_bootstrap as kb,
        knowledge_candidates,
    )

    db = boot_db
    monkeypatch.setattr(
        knowledge_candidates,
        "publish_candidate",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("index unavailable")),
    )
    outline = {"name": "数据结构", "chapters": [{"name": "线性表", "points": [
        {"name": "链表", "objectives": ["掌握链表"]}]}]}
    result = kb.promote_draft_to_knowledge_base(db, 1, "数据结构", "链表", outline, [])
    # Honest failure: never a fake success, and the reason is recorded.
    assert result["ok"] is False
    assert result["reason"] == "PUBLISH_FAILED"
    assert "index unavailable" in result["detail"]
    assert db.query(SystemSubject).filter_by(name="数据结构").count() == 0
    from common.models.learning import KnowledgeCandidate, KnowledgePoint, KnowledgeVersion

    assert db.query(KnowledgePoint).filter_by(name="链表").count() == 0
    assert db.query(KnowledgeVersion).count() == 0
    assert db.query(KnowledgeCandidate).filter_by(knowledge_point="链表").count() == 0
    # No corpus file may survive for the failed publication.
    from common.knowledge_paths import KNOWLEDGE_ROOT

    leftovers = [
        path for path in (KNOWLEDGE_ROOT / "knowledge_base" / "corpus").rglob("candidate_*.md")
        if "链表" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not leftovers
    # The draft itself is still available for personal-mode generation.
    assert kb.build_personal_draft(db, 1, "数据结构", "链表")["outline"]["name"] == "数据结构"
