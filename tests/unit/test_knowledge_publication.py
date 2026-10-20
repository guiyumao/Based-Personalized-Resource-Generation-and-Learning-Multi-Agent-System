from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.models.learning import KnowledgeBuildTask, KnowledgeCandidate, KnowledgeVersion, User
from services.agent_service.app.services import (
    knowledge_candidates,
)
from services.agent_service.app.services import (
    knowledge_publication as publication,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + (tmp_path / "publication.sqlite").as_posix())
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(publication, "SessionLocal", factory)
    monkeypatch.setattr(publication, "KNOWLEDGE_ROOT", tmp_path)
    monkeypatch.setattr(publication, "CORPUS_DIR", tmp_path / "knowledge_base/corpus")
    with factory() as session:
        session.add(User(id=1, username="publication-test", password_hash="unused", role="admin"))
        session.add(
            KnowledgeBuildTask(
                id=1,
                actor_user_id=1,
                client_request_id="source",
                request_hash="hash",
                trigger_source="document_upload",
                operation_type="IMPORT_DOCUMENT",
                status="COMPLETED",
            )
        )
        session.add(
            KnowledgeCandidate(
                id=1,
                creator_user_id=1,
                source_task_id=1,
                subject="math",
                knowledge_point="vector",
                title="Vector",
                content="Vector fixture content for publication test.",
                source_url="upload://fixture",
                source_hash="source",
                content_hash="body",
                status="APPROVED",
                license_name="INTERNAL_TEST_ONLY",
                license_evidence_url="https://example.org/license",
                publication_allowed=True,
            )
        )
        session.commit()
        yield session
    engine.dispose()


def test_visibility_follows_current_sql_even_with_cached_orphan_chunks(db):
    source = "math/candidate_1_body.md"
    rows = [
        {"metadata": {"source": source}, "content": "orphan"},
        {"metadata": {"source": "math/legacy.md"}, "content": "legacy"},
    ]
    assert [r["content"] for r in publication.visible_chunks(rows)] == ["legacy"]
    with publication.verifying(source):
        assert len(publication.visible_chunks(rows)) == 2
        assert (
            publication.visible_chunks([{"metadata": {"source": "math/candidate_2_other.md"}}])
            == []
        )
    version = KnowledgeVersion(
        candidate_id=1,
        version_number=1,
        subject="math",
        knowledge_point="vector",
        title="Vector",
        content="text",
        source_url="upload://fixture",
        content_hash="body",
        corpus_path="knowledge_base/corpus/" + source,
        published_by=1,
    )
    db.add(version)
    db.commit()
    assert len(publication.visible_chunks(rows)) == 2
    version.is_active = False
    db.commit()
    assert [r["content"] for r in publication.visible_chunks(rows)] == ["legacy"]


def test_direct_article_download_cannot_bypass_publication_gate(db, monkeypatch):
    from services.agent_service.app.services import rag
    from services.agent_service.app.services.knowledge_base import KnowledgeBaseService

    payload = {
        "documents": ["PRIVATE_UNCOMMITTED_MARKER"],
        "metadatas": [{"source": "math/candidate_99_pending.md", "chunk_index": 0}],
    }
    monkeypatch.setattr(
        rag,
        "ChromaRetriever",
        lambda: SimpleNamespace(collection=SimpleNamespace(get=lambda **kwargs: payload)),
    )
    assert KnowledgeBaseService().get_indexed_article("indexed-known-source-id") is None


def test_reconciliation_restores_active_files_and_retires_orphans_idempotently(db, monkeypatch):
    root = publication.CORPUS_DIR
    (root / "math").mkdir(parents=True)
    old = root / "math/candidate_1_old.md"
    old.with_suffix(".archived").write_text("Reviewed previous body", encoding="utf-8")
    orphan = root / "math/candidate_1_orphan.md"
    orphan.write_text("Uncommitted body", encoding="utf-8")
    legacy = root / "math/legacy.md"
    legacy.write_text("Keep legacy", encoding="utf-8")
    version = KnowledgeVersion(
        candidate_id=1,
        version_number=1,
        subject="math",
        knowledge_point="vector",
        title="Vector",
        content="Reviewed previous body",
        source_url="upload://fixture",
        content_hash="old",
        corpus_path="knowledge_base/corpus/math/candidate_1_old.md",
        published_by=1,
    )
    db.add(version)
    db.commit()
    from services.agent_service.app.services import knowledge_base_admin

    calls = []
    monkeypatch.setattr(
        knowledge_base_admin, "_run_index_command", lambda **kwargs: calls.append(kwargs["subject"])
    )
    publication.reconcile(db)
    publication.reconcile(db)
    assert old.read_text(encoding="utf-8") == "Reviewed previous body"
    assert not orphan.exists()
    assert orphan.with_suffix(".pending").exists()
    assert legacy.read_text(encoding="utf-8") == "Keep legacy"
    assert calls == ["math", "math"]


def test_lost_execution_rights_prevent_commit_and_invoke_compensation(db, monkeypatch):
    candidate = db.get(KnowledgeCandidate, 1)
    monkeypatch.setattr(knowledge_candidates, "ROOT_DIR", publication.KNOWLEDGE_ROOT)
    expected = "math/candidate_1_body.md"
    monkeypatch.setattr(
        knowledge_candidates, "publish_document_and_reindex", lambda **kwargs: kwargs["verify"]()
    )
    monkeypatch.setattr(
        knowledge_candidates.KnowledgeBaseService,
        "search_indexed",
        lambda *a, **kw: [{"source": expected}],
    )
    compensated = []
    monkeypatch.setattr(publication, "reconcile", lambda *args, **kwargs: compensated.append(True))

    def guard(write_db=None):
        if write_db is not None:
            raise RuntimeError("execution rights revoked")

    with pytest.raises(RuntimeError, match="revoked"):
        knowledge_candidates.publish_candidate(db, candidate, publisher_user_id=1, guard=guard)
    assert compensated == [True]
    assert db.query(KnowledgeVersion).count() == 0
    assert db.get(KnowledgeCandidate, 1).status == "APPROVED"


def test_chroma_write_failure_keeps_reviewed_candidate_unpublished(db, monkeypatch):
    monkeypatch.setattr(knowledge_candidates, "ROOT_DIR", publication.KNOWLEDGE_ROOT)

    def unavailable(**kwargs):
        raise RuntimeError("Chroma unavailable")

    monkeypatch.setattr(knowledge_candidates, "publish_document_and_reindex", unavailable)
    with pytest.raises(RuntimeError, match="Chroma unavailable"):
        knowledge_candidates.publish_candidate(
            db, db.get(KnowledgeCandidate, 1), publisher_user_id=1
        )
    assert db.query(KnowledgeVersion).count() == 0
    assert db.get(KnowledgeCandidate, 1).status == "APPROVED"


def test_stale_generation_context_cannot_reuse_withdrawn_publication(db):
    from common.schemas.agent import ResourceGenerationRequest
    from services.agent_service.app.services.resource_generation import ResourceGenerationService

    service = ResourceGenerationService()
    request = ResourceGenerationRequest(
        user_id=1,
        knowledge_point="vector",
        retrieval_context={
            "knowledge_base_version": service.settings.knowledge_base_version,
            "knowledge_point_id": "vector",
            "retrieved_chunks": [
                {"content": "withdrawn", "metadata": {"source": "math/candidate_99_revoked.md"}}
            ],
        },
    )
    chunks, saved = service._load_retrieval_context(
        request, knowledge_point="vector", resource_type="courseware"
    )
    assert chunks == [] and saved["retrieved_chunks"] == []


def test_database_flush_failure_reconciles_without_publishing(db, monkeypatch):
    monkeypatch.setattr(knowledge_candidates, "ROOT_DIR", publication.KNOWLEDGE_ROOT)
    monkeypatch.setattr(
        knowledge_candidates, "publish_document_and_reindex", lambda **kwargs: kwargs["verify"]()
    )
    monkeypatch.setattr(
        knowledge_candidates.KnowledgeBaseService,
        "search_indexed",
        lambda *a, **kw: [{"source": "math/candidate_1_body.md"}],
    )
    original_flush = db.flush
    compensated = []

    def fail_version_flush(*args, **kwargs):
        if any(isinstance(row, KnowledgeVersion) for row in db.new):
            raise RuntimeError("injected SQL flush failure")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_version_flush)
    monkeypatch.setattr(publication, "reconcile", lambda *a, **kw: compensated.append(True))
    with pytest.raises(RuntimeError, match="SQL flush"):
        knowledge_candidates.publish_candidate(
            db, db.get(KnowledgeCandidate, 1), publisher_user_id=1
        )
    assert compensated == [True]
    assert db.query(KnowledgeVersion).count() == 0
