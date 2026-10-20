"""Authorization tests for the resource-service write endpoints (DEF-007).

Permission matrix under test:

* public read      : ``GET /resources``, ``GET /resources/{id}``
* authenticated    : ``GET /resources/recommendations``, ``POST /{id}/interactions``,
                     ``GET /{id}/download``
* teacher|admin    : ``POST /import-external``, ``POST /{id}/export``,
                     ``PATCH /{id}/status``, ``DELETE /{id}``
* admin + confirm  : ``DELETE /resources``

No test performs a real destructive deletion of catalog data: the single-resource
delete path is only exercised with a non-existent id (proving the auth gate runs
before business logic), and the bulk-delete path is always monkeypatched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.resource_service.app.api.routes.resources import (
    BULK_DELETE_CONFIRMATION_HEADER,
    BULK_DELETE_CONFIRMATION_VALUE,
)
from services.resource_service.app.main import app
from services.resource_service.app.services.resource_manager import ResourceManager

CLIENT = TestClient(app)

# A resource id that is guaranteed absent, so write calls that reach the business
# layer still cannot mutate anything.
ABSENT_RESOURCE_ID = 999_999_999

WRITE_ENDPOINTS = [
    (
        "POST",
        "/resources/import-external",
        {"json": {"title": "t", "provider": "p", "url": "u", "knowledge_point": "k"}},
    ),
    ("POST", f"/resources/{ABSENT_RESOURCE_ID}/export", {"json": {"export_format": "pdf"}}),
    ("PATCH", f"/resources/{ABSENT_RESOURCE_ID}/status", {"json": {"status": "ready"}}),
    ("DELETE", f"/resources/{ABSENT_RESOURCE_ID}", {}),
]

# `auth_headers`, `teacher_headers` and `admin_headers` come from tests/conftest.py.


# --------------------------------------------------------------------- public read
def test_public_read_endpoints_stay_public() -> None:
    """GET /resources and GET /resources/{id} must not be hardened into 401s.

    Their payload (ResourceItem) contains metadata only: title, type, format,
    status, knowledge point, provider, external URL and the *relative* download
    URL. No local filesystem path, no credential, no per-user private field is
    exposed, so the read-only catalog contract is preserved.
    """

    listing = CLIENT.get("/resources")
    assert listing.status_code == 200, "resource catalog unexpectedly requires auth"

    items = listing.json().get("data") or []
    if items:
        detail = CLIENT.get(f"/resources/{items[0]['id']}")
        assert detail.status_code == 200

    absent = CLIENT.get(f"/resources/{ABSENT_RESOURCE_ID}")
    assert absent.status_code == 404


def test_public_read_payload_has_no_local_paths() -> None:
    """The public catalog must not leak absolute local file paths."""

    items = CLIENT.get("/resources").json().get("data") or []
    for item in items:
        assert "absolute_path" not in item
        assert "local_path" not in item
        for key in ("external_url", "download_url", "notes", "file_name"):
            value = item.get(key)
            if not isinstance(value, str):
                continue
            # Windows drive paths, UNC shares and multi-segment relative paths
            # would expose server filesystem layout.
            assert ":\\" not in value, f"{key} leaks a drive path: {value}"
            assert "\\\\" not in value, f"{key} leaks a UNC path: {value}"
            assert not value.startswith("../"), f"{key} traverses upwards: {value}"


# ------------------------------------------------------------------------ anonymous
@pytest.mark.parametrize("method,path,kwargs", WRITE_ENDPOINTS)
def test_anonymous_write_requests_are_401(method: str, path: str, kwargs: dict) -> None:
    """Every write endpoint must reject unauthenticated callers with 401."""

    response = CLIENT.request(method, path, **kwargs)
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


def test_anonymous_bulk_delete_is_401() -> None:
    """Bulk delete must not be reachable anonymously (401 before the confirm check)."""

    response = CLIENT.delete("/resources")
    assert response.status_code == 401


def test_anonymous_download_is_401() -> None:
    """The download endpoint streams local file bytes and must require auth."""

    response = CLIENT.get(f"/resources/{ABSENT_RESOURCE_ID}/download")
    assert response.status_code == 401


# -------------------------------------------------------------------- student 403
@pytest.mark.parametrize("method,path,kwargs", WRITE_ENDPOINTS)
def test_student_write_requests_are_403(method: str, path: str, kwargs: dict, auth_headers) -> None:
    """A learner token must be refused (403) on teacher/admin write endpoints."""

    response = CLIENT.request(method, path, headers=auth_headers, **kwargs)
    assert response.status_code == 403, f"{method} {path} -> {response.status_code}"


def test_student_bulk_delete_is_403(auth_headers) -> None:
    """Bulk delete requires admin; a learner token is 403 even with confirmation."""

    response = CLIENT.delete(
        "/resources",
        headers={**auth_headers, BULK_DELETE_CONFIRMATION_HEADER: BULK_DELETE_CONFIRMATION_VALUE},
    )
    assert response.status_code == 403


def test_student_download_reaches_business_layer(auth_headers) -> None:
    """Authenticated learners keep download access; absent resource -> 404, not 401/403."""

    response = CLIENT.get(f"/resources/{ABSENT_RESOURCE_ID}/download", headers=auth_headers)
    assert response.status_code == 404


# ------------------------------------------------------------------- teacher path
def test_teacher_import_reaches_business_layer(monkeypatch, teacher_headers) -> None:
    """teacher passes the auth gate and reaches ResourceManager (mocked here)."""

    calls: list[str] = []

    def fake_import(self, payload):
        calls.append(payload.title)
        return {
            "id": 4242,
            "title": payload.title,
            "type": "courseware",
            "format": "pdf",
            "status": "ready",
            "knowledge_point": payload.knowledge_point,
            "owner_user_id": None,
            "source_type": "external_import",
            "provider": payload.provider,
            "source_kind": payload.kind,
            "external_url": payload.url,
            "download_url": "/resources/4242/download",
            "notes": payload.notes,
            "file_name": "x.pdf",
            "is_downloadable": True,
        }

    monkeypatch.setattr(ResourceManager, "import_external_resource", fake_import)

    response = CLIENT.post(
        "/resources/import-external",
        headers=teacher_headers,
        json={
            "title": "Teacher import",
            "provider": "Example",
            "url": "https://example.com/a.pdf",
            "knowledge_point": "Python 循环",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["id"] == 4242
    assert calls == ["Teacher import"]


def test_teacher_export_absent_resource_is_404(teacher_headers) -> None:
    """teacher authorizes and gets the original business error semantics."""

    response = CLIENT.post(
        f"/resources/{ABSENT_RESOURCE_ID}/export",
        headers=teacher_headers,
        json={"export_format": "pdf"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"


def test_teacher_patch_status_absent_resource_is_404(teacher_headers) -> None:
    """teacher authorizes; unknown id keeps the 404 contract."""

    response = CLIENT.patch(
        f"/resources/{ABSENT_RESOURCE_ID}/status",
        headers=teacher_headers,
        json={"status": "ready"},
    )
    assert response.status_code == 404


def test_teacher_single_delete_absent_resource_is_404(teacher_headers) -> None:
    """teacher authorizes; deleting an absent id yields 404 and removes nothing."""

    response = CLIENT.delete(f"/resources/{ABSENT_RESOURCE_ID}", headers=teacher_headers)
    assert response.status_code == 404


# --------------------------------------------------------------------- admin paths
def test_admin_single_delete_absent_resource_is_404(admin_headers) -> None:
    """admin authorizes on single delete; absent id -> 404."""

    response = CLIENT.delete(f"/resources/{ABSENT_RESOURCE_ID}", headers=admin_headers)
    assert response.status_code == 404


def test_admin_bulk_delete_requires_confirmation_header(monkeypatch, admin_headers) -> None:
    """admin without the confirmation header must be refused before any deletion."""

    called: list[object] = []
    monkeypatch.setattr(
        ResourceManager,
        "delete_all_resources",
        lambda self, source_type=None: called.append(source_type) or 0,
    )

    response = CLIENT.delete("/resources", headers=admin_headers)
    assert response.status_code == 400
    assert BULK_DELETE_CONFIRMATION_HEADER in response.json()["detail"]
    assert called == [], "manager was invoked without explicit confirmation"


def test_admin_bulk_delete_with_wrong_confirmation_value(monkeypatch, admin_headers) -> None:
    """A wrong confirmation value is still refused."""

    monkeypatch.setattr(ResourceManager, "delete_all_resources", lambda self, source_type=None: 0)
    response = CLIENT.delete(
        "/resources", headers={**admin_headers, BULK_DELETE_CONFIRMATION_HEADER: "yes"}
    )
    assert response.status_code == 400


def test_admin_bulk_delete_passes_gate_but_is_mocked(monkeypatch, admin_headers) -> None:
    """admin + confirmation passes auth and forwards source_type — deletion is mocked."""

    captured: dict[str, object] = {}

    def fake_delete_all(self, source_type=None):
        captured["source_type"] = source_type
        return 7

    monkeypatch.setattr(ResourceManager, "delete_all_resources", fake_delete_all)

    response = CLIENT.delete(
        "/resources",
        params={"source_type": "generated"},
        headers={**admin_headers, BULK_DELETE_CONFIRMATION_HEADER: BULK_DELETE_CONFIRMATION_VALUE},
    )
    assert response.status_code == 200
    assert response.json()["data"]["deleted_count"] == 7
    assert captured["source_type"] == "generated"


def test_bulk_delete_rejects_invalid_source_type_with_confirmation(
    monkeypatch, admin_headers
) -> None:
    """Invalid source_type keeps the original 400 contract."""

    monkeypatch.setattr(ResourceManager, "delete_all_resources", lambda self, source_type=None: 0)
    response = CLIENT.delete(
        "/resources",
        params={"source_type": "bogus"},
        headers={**admin_headers, BULK_DELETE_CONFIRMATION_HEADER: BULK_DELETE_CONFIRMATION_VALUE},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid source_type"
