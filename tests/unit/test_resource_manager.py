"""Unit tests for the resource manager import workflow."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi.testclient import TestClient

from common.models.learning import KnowledgePoint, Resource, ResourceInteraction, User
from services.resource_service.app.main import app
from services.resource_service.app.schemas.resource import ExternalResourceImportRequest
from services.resource_service.app.services.resource_manager import ResourceManager


def test_import_external_route_is_not_shadowed_by_resource_id(monkeypatch, teacher_headers) -> None:
    """Static import route should handle POST before the dynamic resource ID route.

    ``POST /resources/import-external`` now requires teacher|admin (DEF-007), so the
    test presents a teacher token.
    """

    def fake_import_external_resource(self, payload):
        return {
            "id": 999,
            "title": payload.title,
            "type": "courseware",
            "format": "pdf",
            "status": "ready",
            "knowledge_point": payload.knowledge_point,
            "owner_user_id": payload.owner_user_id,
            "source_type": "external_import",
            "provider": payload.provider,
            "source_kind": payload.kind,
            "external_url": payload.url,
            "download_url": "/resources/999/download",
            "notes": payload.notes,
            "file_name": "sample.pdf",
            "is_downloadable": True,
        }

    monkeypatch.setattr(ResourceManager, "import_external_resource", fake_import_external_resource)

    client = TestClient(app)
    response = client.post(
        "/resources/import-external",
        headers=teacher_headers,
        json={
            "title": "Sample Courseware",
            "provider": "Example University",
            "url": "https://example.com/courseware.pdf",
            "kind": "lecture_notes",
            "license": "CC BY",
            "notes": "Official notes",
            "knowledge_point": "Python 循环",
            "owner_user_id": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["id"] == 999
    assert payload["data"]["source_type"] == "external_import"


def test_import_external_resource_creates_downloadable_item(db_session, monkeypatch) -> None:
    """Imported external courseware should be persisted as a downloadable managed resource."""

    manager = ResourceManager(db_session)
    monkeypatch.setattr(
        manager,
        "_download_external_asset",
        lambda url, title: {
            "relative_path": "storage/resources/sample-courseware.pdf",
            "file_name": "sample-courseware.pdf",
            "mime_type": "application/pdf",
            "format": "pdf",
        },
    )

    item = manager.import_external_resource(
        ExternalResourceImportRequest(
            title="MIT Linear Algebra Notes",
            provider="MIT OpenCourseWare",
            url="https://example.com/linear-algebra.pdf",
            kind="mooc_course",
            license="CC BY-NC-SA 4.0",
            notes="Official lecture notes",
            knowledge_point="线性代数",
            owner_user_id=None,
        )
    )

    assert item.source_type == "external_import"
    assert item.provider == "MIT OpenCourseWare"
    assert item.format == "pdf"
    assert item.is_downloadable is True
    assert item.download_url == f"/resources/{item.id}/download"

    stored = db_session.get(Resource, item.id)
    assert stored is not None
    metadata = json.loads(stored.content)
    assert metadata["mode"] == "external_import"
    assert metadata["external_url"] == "https://example.com/linear-algebra.pdf"

    db_session.delete(stored)
    knowledge_point = db_session.query(KnowledgePoint).filter(KnowledgePoint.name == "线性代数").first()
    if knowledge_point is not None:
        db_session.delete(knowledge_point)
    db_session.commit()


def test_delete_all_resources_can_filter_by_source_type(monkeypatch, admin_headers) -> None:
    """Bulk delete route should forward source_type to the manager.

    The route is now admin-only and additionally requires the explicit
    confirmation header (DEF-007); the manager call itself stays mocked so this
    test never deletes real catalog data.
    """

    captured: dict[str, str | None] = {}

    def fake_delete_all_resources(self, source_type=None):
        captured["source_type"] = source_type
        return 7

    monkeypatch.setattr(ResourceManager, "delete_all_resources", fake_delete_all_resources)

    client = TestClient(app)
    response = client.delete(
        "/resources",
        params={"source_type": "generated"},
        headers={**admin_headers, "X-Confirm-Delete-All": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["deleted_count"] == 7
    assert captured["source_type"] == "generated"


def test_recommendations_use_authenticated_learning_behaviour(db_session, test_user) -> None:
    """A learner's viewed topic should outrank an otherwise similar unseen topic."""

    suffix = uuid4().hex[:8]
    network_point = KnowledgePoint(name=f"计算机网络-{suffix}", description="", difficulty=2, importance=3)
    os_point = KnowledgePoint(name=f"操作系统-{suffix}", description="", difficulty=2, importance=3)
    db_session.add_all([network_point, os_point])
    db_session.commit()
    network_resource = Resource(
        title="TCP 可靠传输讲义",
        type="courseware",
        content="# TCP 可靠传输讲义",
        format="markdown",
        knowledge_point_id=network_point.id,
        publish_status="published",
        audit_status="passed",
    )
    os_resource = Resource(
        title="进程调度讲义",
        type="courseware",
        content="# 进程调度讲义",
        format="markdown",
        knowledge_point_id=os_point.id,
        publish_status="published",
        audit_status="passed",
    )
    db_session.add_all([network_resource, os_resource])
    db_session.commit()

    manager = ResourceManager(db_session)
    first_view = manager.record_interaction(test_user.id, network_resource.id, "view")
    duplicate_view = manager.record_interaction(test_user.id, network_resource.id, "view")
    download = manager.record_interaction(test_user.id, network_resource.id, "download")
    recommendations = manager.recommend_resources(test_user.id, limit=2)

    assert first_view is not None and first_view.recorded is True
    assert duplicate_view is not None and duplicate_view.recorded is False
    assert download is not None and download.download_count == 1
    assert recommendations[0].id == network_resource.id
    assert recommendations[0].recommendation_reason.startswith("延续你对")
    assert recommendations[0].view_count == 1
    assert recommendations[0].download_count == 1

    resource_ids = [network_resource.id, os_resource.id]
    db_session.query(ResourceInteraction).filter(ResourceInteraction.resource_id.in_(resource_ids)).delete(
        synchronize_session=False
    )
    db_session.query(Resource).filter(Resource.id.in_(resource_ids)).delete(synchronize_session=False)
    db_session.query(KnowledgePoint).filter(KnowledgePoint.id.in_([network_point.id, os_point.id])).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_recommendations_require_authentication() -> None:
    client = TestClient(app)
    response = client.get("/resources/recommendations")

    assert response.status_code == 401


def test_recommendations_use_user_and_item_collaborative_filtering(db_session, test_user) -> None:
    """Similar learners and co-consumed resources should create CF signals."""

    suffix = uuid4().hex[:8]
    peer = User(
        username=f"pytest_cf_peer_{suffix}",
        password_hash="test-only-password-hash",
        role="student",
        email=f"pytest_cf_peer_{suffix}@example.com",
    )
    shared_point = KnowledgePoint(name=f"共享知识点-{suffix}", description="", difficulty=2, importance=3)
    related_point = KnowledgePoint(name=f"关联知识点-{suffix}", description="", difficulty=2, importance=3)
    unrelated_point = KnowledgePoint(name=f"无关知识点-{suffix}", description="", difficulty=2, importance=3)
    db_session.add_all([peer, shared_point, related_point, unrelated_point])
    db_session.commit()

    shared_resource = Resource(
        title="共享资源",
        type="courseware",
        content="# 共享资源",
        format="markdown",
        knowledge_point_id=shared_point.id,
        publish_status="published",
        audit_status="passed",
    )
    related_resource = Resource(
        title="相似学习者正在学习的资源",
        type="courseware",
        content="# 相似学习者正在学习的资源",
        format="markdown",
        knowledge_point_id=related_point.id,
        publish_status="published",
        audit_status="passed",
    )
    unrelated_resource = Resource(
        title="无关资源",
        type="courseware",
        content="# 无关资源",
        format="markdown",
        knowledge_point_id=unrelated_point.id,
        publish_status="published",
        audit_status="passed",
    )
    db_session.add_all([shared_resource, related_resource, unrelated_resource])
    db_session.commit()

    db_session.add_all(
        [
            ResourceInteraction(user_id=test_user.id, resource_id=shared_resource.id, action="view", knowledge_point=shared_point.name),
            ResourceInteraction(user_id=peer.id, resource_id=shared_resource.id, action="view", knowledge_point=shared_point.name),
            ResourceInteraction(user_id=peer.id, resource_id=related_resource.id, action="download", knowledge_point=related_point.name),
        ]
    )
    db_session.commit()

    recommendations = ResourceManager(db_session).recommend_resources(test_user.id, limit=3)
    by_id = {item.id: item for item in recommendations}

    assert by_id[related_resource.id].recommendation_strategy == "hybrid_collaborative"
    assert by_id[related_resource.id].user_cf_score > 0
    assert by_id[related_resource.id].item_cf_score > 0
    assert by_id[related_resource.id].recommendation_score > by_id[unrelated_resource.id].recommendation_score

    resource_ids = [shared_resource.id, related_resource.id, unrelated_resource.id]
    db_session.query(ResourceInteraction).filter(ResourceInteraction.resource_id.in_(resource_ids)).delete(
        synchronize_session=False
    )
    db_session.query(Resource).filter(Resource.id.in_(resource_ids)).delete(synchronize_session=False)
    db_session.query(KnowledgePoint).filter(
        KnowledgePoint.id.in_([shared_point.id, related_point.id, unrelated_point.id])
    ).delete(synchronize_session=False)
    db_session.delete(peer)
    db_session.commit()
