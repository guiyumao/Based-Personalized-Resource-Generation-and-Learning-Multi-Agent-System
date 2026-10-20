from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import KnowledgeBuildTask, KnowledgeCandidate, KnowledgeVersion, User
from services.agent_service.app.main import app
from services.agent_service.app.services import knowledge_candidates


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'candidates.db'}")
    maker = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with maker() as db:
        db.add(User(id=1, username="admin", password_hash="unused", role="admin"))
        db.add(KnowledgeBuildTask(
            id=10, actor_user_id=1, client_request_id="fetch", request_hash="x" * 64,
            trigger_source="ADMIN_MANUAL", operation_type="FETCH_SOURCE", subject="computer_networks",
            requirements_json={}, status="COMPLETED", current_step="done", error_code="",
            result_json={"review_status": "PENDING", "source": {
                "url": "https://example.edu/bbr", "title": "BBR congestion control",
                "content": "BBR estimates bottleneck bandwidth and round trip propagation time for congestion control.",
            }},
        ))
        db.commit()
    monkeypatch.setattr(knowledge_candidates, "ROOT_DIR", tmp_path)
    yield maker, tmp_path
    engine.dispose()


def test_review_publish_and_idempotent_version(factory, monkeypatch) -> None:
    maker, root = factory
    def publish_file(**kwargs):
        kwargs["target"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["target"].write_text(kwargs["content"], encoding="utf-8")
        return {"ok": True}
    monkeypatch.setattr(knowledge_candidates, "publish_document_and_reindex", publish_file)
    monkeypatch.setattr(
        knowledge_candidates.KnowledgeBaseService, "search_indexed",
        lambda self, *_args, **_kwargs: [{"metadata": {"source": "computer_networks/candidate_1_expected.md"}}],
    )
    with maker() as db:
        item = knowledge_candidates.create_from_fetch(
            db, actor_user_id=1, source_task_id=10, subject="computer_networks", knowledge_point="BBR",
        )
        duplicate = knowledge_candidates.create_from_fetch(
            db, actor_user_id=1, source_task_id=10, subject="computer_networks", knowledge_point="ignored",
        )
        assert duplicate.id == item.id
        knowledge_candidates.edit_candidate(db, item, content=item.content + " It also tracks inflight data.")
        knowledge_candidates.edit_candidate(db, item, license_name="INTERNAL_TEST_ONLY", license_evidence_url="https://example.edu/permissions", publication_allowed=True)
        knowledge_candidates.submit_candidate(db, item)
        with pytest.raises(knowledge_candidates.KnowledgeCandidateConflict):
            knowledge_candidates.publish_candidate(db, item, publisher_user_id=1)
        knowledge_candidates.review_candidate(db, item, reviewer_user_id=1, approved=True, notes="source checked")
        expected = f"computer_networks/candidate_{item.id}_{item.content_hash[:12]}.md"
        monkeypatch.setattr(
            knowledge_candidates.KnowledgeBaseService, "search_indexed",
            lambda self, *_args, **_kwargs: [{"source": expected}],
        )
        version, matches = knowledge_candidates.publish_candidate(db, item, publisher_user_id=1)
        again, second_matches = knowledge_candidates.publish_candidate(db, item, publisher_user_id=1)
        assert version.id == again.id
        assert matches and second_matches == matches  # Replay re-verifies live retrieval.
        assert db.query(KnowledgeVersion).count() == 1
        assert db.get(KnowledgeCandidate, item.id).status == "PUBLISHED"
        assert (root / version.corpus_path).exists()
        from services.agent_service.app.services import knowledge_versions
        monkeypatch.setattr(knowledge_versions, "KNOWLEDGE_ROOT", root)
        monkeypatch.setattr(knowledge_versions, "publish_document_and_reindex", publish_file)
        knowledge_candidates.start_revision(db, item)
        knowledge_candidates.submit_candidate(db, item)
        knowledge_candidates.review_candidate(db, item, reviewer_user_id=1, approved=True, notes="same body reviewed again")
        reused, _ = knowledge_candidates.publish_candidate(db, item, publisher_user_id=1)
        assert reused.id == version.id
        assert item.status == "PUBLISHED" and reused.is_active


def test_candidate_api_permissions_and_workflow(factory) -> None:
    maker, _root = factory
    client = TestClient(app)
    assert client.get("/knowledge-base/candidates").status_code == 401
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="admin")
    app.dependency_overrides[get_db] = lambda: maker()
    try:
        created = client.post("/knowledge-base/candidates", json={
            "source_task_id": 10, "subject": "computer_networks", "knowledge_point": "BBR",
        })
        assert created.status_code == 201
        candidate_id = created.json()["id"]
        assert client.post(f"/knowledge-base/candidates/{candidate_id}/publish").status_code == 409
        assert client.post(f"/knowledge-base/candidates/{candidate_id}/submit").json()["status"] == "PENDING_REVIEW"
        reviewed = client.post(f"/knowledge-base/candidates/{candidate_id}/review", json={"decision": "APPROVE", "notes": "verified"})
        assert reviewed.json()["status"] == "APPROVED"
        assert len(client.get("/knowledge-base/candidates").json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_approval_does_not_imply_source_permission(factory):
    maker, _root = factory
    with maker() as db:
        item = knowledge_candidates.create_from_fetch(db, actor_user_id=1, source_task_id=10, subject="computer_networks", knowledge_point="BBR")
        knowledge_candidates.submit_candidate(db, item)
        knowledge_candidates.review_candidate(db, item, reviewer_user_id=1, approved=True, notes="content checked")
        with pytest.raises(knowledge_candidates.KnowledgeCandidateConflict, match="permission"):
            knowledge_candidates.publish_candidate(db, item, publisher_user_id=1)
