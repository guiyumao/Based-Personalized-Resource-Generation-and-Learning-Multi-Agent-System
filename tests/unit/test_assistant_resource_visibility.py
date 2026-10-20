"""An assistant-generated private resource is readable only by its learner."""

from __future__ import annotations

from fastapi.testclient import TestClient

from common.models.learning import Resource
from common.security.auth import create_access_token
from services.resource_service.app.main import app


def test_generated_resource_is_isolated(db_session, test_user, other_user, auth_headers, teacher_headers, admin_headers):
    item = Resource(
        title="Private assistant lesson",
        type="courseware",
        content="User-specific learning material",
        format="markdown",
        generated_for_user_id=test_user.id,
        generation_status="generated",
        audit_status="passed",
        publish_status="draft",
    )
    db_session.add(item)
    db_session.commit()
    try:
        client = TestClient(app)
        own = client.get(f"/resources/{item.id}", headers=auth_headers)
        assert own.status_code == 200
        assert own.json()["data"]["content"] == item.content
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other_user.id))}"}
        assert client.get(f"/resources/{item.id}").status_code == 404
        assert client.get(f"/resources/{item.id}", headers=other_headers).status_code == 404
        assert item.id in {row["id"] for row in client.get("/resources", headers=auth_headers).json()["data"]}
        assert item.id not in {row["id"] for row in client.get("/resources").json()["data"]}
        assert item.id not in {row["id"] for row in client.get("/resources", headers=other_headers).json()["data"]}
        export = client.post(f"/resources/{item.id}/export", headers=teacher_headers, json={"export_format": "pdf"})
        assert export.status_code == 404
        admin_export = client.post(f"/resources/{item.id}/export", headers=admin_headers, json={"export_format": "pdf"})
        assert admin_export.status_code == 501
        assert "download_url" not in admin_export.json()
        assert client.patch(f"/resources/{item.id}/status", headers=teacher_headers, json={"status": "ready"}).status_code == 404
        assert client.delete(f"/resources/{item.id}", headers=teacher_headers).status_code == 404
    finally:
        db_session.delete(item)
        db_session.commit()
