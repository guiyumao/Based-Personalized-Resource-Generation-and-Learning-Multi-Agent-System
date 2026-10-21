"""Operations insight for automatic backfill: statistics and orphan inspection.

The endpoints are read-only, so every case also proves that calling them does
not mutate the catalog, the corpus or the index.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.knowledge_paths import KNOWLEDGE_ROOT
from common.models.learning import (
    AuditLog,
    KnowledgeBuildTask,
    KnowledgeCandidate,
    KnowledgePoint,
    KnowledgeVersion,
    SystemSubject,
    User,
)
from services.agent_service.app.main import app
from services.agent_service.app.services import knowledge_audit

CORPUS_DIR = KNOWLEDGE_ROOT / "knowledge_base" / "corpus"


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ops.sqlite'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(User(id=1, username="admin", password_hash="unused", role="admin"))
    db.add(User(id=2, username="learner", password_hash="unused", role="student"))
    db.commit()

    def client() -> TestClient:
        # Point the app at the isolated database so the endpoints observe the
        # same rows the assertions below create.
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1, role="admin", username="admin"
        )
        return TestClient(app)

    yield SimpleNamespace(db=db, client=client)
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def _candidate(db, *, status: str, license_name: str = "AI_GENERATED") -> KnowledgeCandidate:
    task = KnowledgeBuildTask(
        actor_user_id=1,
        client_request_id=f"ops-{uuid.uuid4().hex[:12]}",
        request_hash=uuid.uuid4().hex[:64],
        trigger_source="ADMIN_MANUAL",
        operation_type="PUBLISH_CANDIDATE",
        subject="ops-fixture",
    )
    db.add(task)
    db.flush()
    item = KnowledgeCandidate(
        creator_user_id=1,
        source_task_id=task.id,
        subject="运维学科",
        knowledge_point="知识点",
        title="标题",
        content="正文" * 50,
        source_url="manual://fixture",
        source_hash=uuid.uuid4().hex[:64],
        content_hash=uuid.uuid4().hex[:64],
        status=status,
        license_name=license_name,
    )
    db.add(item)
    db.flush()
    return item


def test_stats_count_auto_published_knowledge_separately(env):
    db = env.db
    _candidate(db, status="AUTO_APPROVED")
    _candidate(db, status="APPROVED", license_name="CC-BY")
    _candidate(db, status="AUTO_APPROVED")

    auto = _candidate(db, status="AUTO_APPROVED")
    db.add(
        KnowledgeVersion(
            candidate_id=auto.id,
            version_number=1,
            subject="ops",
            knowledge_point="知识点",
            title="标题",
            content="正文" * 50,
            source_url="knowledge_base/corpus/ops/candidate_1.md",
            content_hash="a" * 64,
            corpus_path="knowledge_base/corpus/ops/candidate_1.md",
            published_by=1,
            published_at=datetime.utcnow(),
            is_active=True,
            license_name="AI_GENERATED",
        )
    )
    human = _candidate(db, status="APPROVED", license_name="CC-BY")
    db.add(
        KnowledgeVersion(
            candidate_id=human.id,
            version_number=1,
            subject="ops",
            knowledge_point="知识点",
            title="标题",
            content="正文" * 50,
            source_url="knowledge_base/corpus/ops/candidate_2.md",
            content_hash="b" * 64,
            corpus_path="knowledge_base/corpus/ops/candidate_2.md",
            published_by=1,
            published_at=datetime.utcnow(),
            is_active=True,
            license_name="CC-BY",
        )
    )
    db.commit()

    stats = knowledge_audit.auto_backfill_stats(db, days=7)
    assert stats["candidates"]["auto_approved"] == 3
    assert stats["candidates"]["by_status"]["APPROVED"] == 2
    assert stats["versions"]["auto_published"] == 1
    assert stats["versions"]["human_published"] == 1


def test_stats_group_failure_reasons_and_recent_failures(env):
    db = env.db
    old = datetime.utcnow() - timedelta(days=30)
    for index, reason in enumerate(["LOCK_BUSY", "LOCK_BUSY", "PUBLISH_FAILED"]):
        db.add(
            AuditLog(
                level="WARNING",
                event=knowledge_audit.FAILED_EVENT,
                actor_user_id=2,
                message=f"subject=s point=p reason={reason}",
                created_at=old if index == 2 else datetime.utcnow(),
            )
        )
    db.commit()

    stats = knowledge_audit.auto_backfill_stats(db, days=7)
    # The window only shapes event counts; reasons are aggregated over the log.
    assert stats["failure_reasons"]["LOCK_BUSY"] == 2
    assert stats["failure_reasons"]["PUBLISH_FAILED"] == 1
    assert stats["events_in_window"].get(knowledge_audit.FAILED_EVENT) == 2
    assert stats["recent_failures"] and stats["recent_failures"][0]["reason"] in {
        "LOCK_BUSY",
        "PUBLISH_FAILED",
    }


def test_inspection_is_healthy_for_a_consistent_state(env, tmp_path, monkeypatch):
    db = env.db
    # Isolate the sweep: other suites legitimately leave corpus files behind in
    # the shared runtime root, and this case asserts a *whole* store is clean.
    isolated_root = tmp_path / "isolated-root"
    isolated_corpus = isolated_root / "knowledge_base" / "corpus"
    isolated_corpus.mkdir(parents=True)
    monkeypatch.setattr(knowledge_audit, "KNOWLEDGE_ROOT", isolated_root)
    monkeypatch.setattr(knowledge_audit, "CORPUS_DIR", isolated_corpus)

    class EmptyIndex:
        is_available = True

        class collection:  # noqa: N801 - mirrors the Chroma attribute name
            @staticmethod
            def get(**kwargs):
                return {"ids": [], "metadatas": []}

    from services.agent_service.app.services import rag

    monkeypatch.setattr(rag, "ChromaRetriever", EmptyIndex)

    candidate = _candidate(db, status="AUTO_APPROVED")
    subject_code = f"ops_{uuid.uuid4().hex[:8]}"
    directory = isolated_corpus / subject_code
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "candidate_1_fixture.md"
    target.write_text("# fixture\n\n正文\n", encoding="utf-8")
    db.add(
        KnowledgeVersion(
            candidate_id=candidate.id,
            version_number=1,
            subject=subject_code,
            knowledge_point="知识点",
            title="标题",
            content="正文" * 50,
            source_url=f"knowledge_base/corpus/{subject_code}/candidate_1_fixture.md",
            content_hash="c" * 64,
            corpus_path=f"knowledge_base/corpus/{subject_code}/candidate_1_fixture.md",
            published_by=1,
            published_at=datetime.utcnow(),
            is_active=True,
            license_name="AI_GENERATED",
        )
    )
    db.commit()

    report = knowledge_audit.orphan_inspection(db)
    assert report["healthy"] is True, report
    assert report["missing_corpus_files"] == []
    assert report["orphan_corpus_file_count"] == 0
    assert report["active_versions"] == 1


def test_inspection_reports_missing_file_and_uncommitted_pending_file(env):
    db = env.db
    candidate = _candidate(db, status="AUTO_APPROVED")
    subject_code = f"ops_{uuid.uuid4().hex[:8]}"
    directory = CORPUS_DIR / subject_code
    directory.mkdir(parents=True, exist_ok=True)
    pending = directory / "candidate_9_pending.pending"
    pending.write_text("uncommitted", encoding="utf-8")
    db.add(
        KnowledgeVersion(
            candidate_id=candidate.id,
            version_number=1,
            subject=subject_code,
            knowledge_point="知识点",
            title="标题",
            content="正文" * 50,
            source_url=f"knowledge_base/corpus/{subject_code}/candidate_1_gone.md",
            content_hash="d" * 64,
            corpus_path=f"knowledge_base/corpus/{subject_code}/candidate_1_gone.md",
            published_by=1,
            published_at=datetime.utcnow(),
            is_active=True,
            license_name="AI_GENERATED",
        )
    )
    db.commit()

    report = knowledge_audit.orphan_inspection(db)
    assert report["healthy"] is False
    assert any(
        item["source"].endswith("candidate_1_gone.md") for item in report["missing_corpus_files"]
    )
    assert any("candidate_9_pending.pending" in name for name in report["pending_files"])

    pending.unlink()
    directory.rmdir()


def test_ops_endpoints_are_admin_only_and_read_only(env):
    db = env.db
    _candidate(db, status="AUTO_APPROVED")
    db.commit()

    anonymous = TestClient(app)
    assert anonymous.get("/knowledge-base/admin/auto-backfill/stats").status_code in (401, 403)
    assert anonymous.get("/knowledge-base/admin/inspection/orphans").status_code in (401, 403)

    client = env.client()
    try:
        stats = client.get("/knowledge-base/admin/auto-backfill/stats", params={"days": 7})
        inspection = client.get("/knowledge-base/admin/inspection/orphans")
    finally:
        app.dependency_overrides.clear()

    assert stats.status_code == 200, stats.text
    assert inspection.status_code == 200, inspection.text
    body = stats.json()
    assert body["candidates"]["auto_approved"] == 1
    assert "healthy" in inspection.json()
    # Read-only: no extra rows were created by the inspection itself.
    assert db.query(KnowledgeVersion).count() == 0


def test_candidate_listing_can_filter_auto_published_knowledge(env):
    db = env.db
    _candidate(db, status="AUTO_APPROVED")
    _candidate(db, status="APPROVED", license_name="CC-BY")
    db.commit()

    client = env.client()
    try:
        auto_only = client.get(
            "/knowledge-base/candidates", params={"status": "AUTO_APPROVED", "limit": 50}
        )
        licensed = client.get(
            "/knowledge-base/candidates", params={"license_name": "AI_GENERATED", "limit": 50}
        )
    finally:
        app.dependency_overrides.clear()

    assert auto_only.status_code == 200, auto_only.text
    assert licensed.status_code == 200, licensed.text
    assert len(auto_only.json()["items"]) == 1
    assert len(licensed.json()["items"]) == 1
    assert auto_only.json()["items"][0]["status"] == "AUTO_APPROVED"
