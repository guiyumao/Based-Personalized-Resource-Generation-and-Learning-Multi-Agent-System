"""Unit tests for the resource manager import workflow."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from common.models.learning import KnowledgePoint, Resource
from services.resource_service.app.schemas.resource import ExternalResourceImportRequest
from services.resource_service.app.main import app
from services.resource_service.app.services.resource_manager import ResourceManager


def test_import_external_route_is_not_shadowed_by_resource_id(monkeypatch) -> None:
    """Static import route should handle POST before the dynamic resource ID route."""

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
