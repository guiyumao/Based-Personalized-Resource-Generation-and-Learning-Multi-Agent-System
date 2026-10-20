"""Authorization and leak-prevention tests for GET /system/configs (DEF-006).

The endpoint was anonymously readable because a docstring declared it "PUBLIC".
Config values are free-form strings written by administrators, so the table can
hold credentials; the endpoint is now admin-only and additionally filters any
entry whose key looks like a secret.

No real config row is written by these tests: the manager is monkeypatched so the
shared development database is never polluted with fake secrets.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.system_service.app.api.routes.admin import _filter_configs, _is_sensitive_key
from services.system_service.app.main import app
from services.system_service.app.schemas.system import SystemConfigItem
from services.system_service.app.services.system_persistence import SystemManager

CLIENT = TestClient(app)


def test_anonymous_config_read_is_401() -> None:
    """SEC-ANON: the config listing must not be world readable."""

    assert CLIENT.get("/system/configs").status_code == 401


def test_student_config_read_is_403(auth_headers) -> None:
    """A learner token is insufficient for system configuration."""

    assert CLIENT.get("/system/configs", headers=auth_headers).status_code == 403


def test_teacher_config_read_is_403(teacher_headers) -> None:
    """teacher is not admin either."""

    assert CLIENT.get("/system/configs", headers=teacher_headers).status_code == 403


def test_admin_config_read_succeeds(monkeypatch, admin_headers) -> None:
    """admin reaches the listing; the payload keeps its original shape."""

    monkeypatch.setattr(
        SystemManager,
        "list_configs",
        lambda self: [SystemConfigItem(key="ui.theme", value="light")],
    )
    response = CLIENT.get("/system/configs", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"] == [{"key": "ui.theme", "value": "light"}]


@pytest.mark.parametrize(
    "key",
    [
        "JWT_SECRET_KEY",
        "jwt_secret_key",
        "database_url",
        "DATABASE_URL",
        "postgres_password",
        "redis_connection_string",
        "deepseek_api_key",
        "minio_secret_key",
        "rabbitmq_password",
        "session_key",
        "smtp_password",
        "webhook_signing_secret",
        "fernet_private_key",
        "password_salt",
    ],
)
def test_sensitive_keys_are_recognised(key: str) -> None:
    """The sensitive-key detector covers the credential shapes this project uses."""

    assert _is_sensitive_key(key) is True


@pytest.mark.parametrize(
    "key",
    ["ui.theme", "feature.qa.enabled", "courseware.variant_count", "rag.retrieval_top_k"],
)
def test_benign_keys_are_not_flagged(key: str) -> None:
    """Non-sensitive configuration must keep working."""

    assert _is_sensitive_key(key) is False


def test_sensitive_values_are_filtered_even_for_admin(monkeypatch, admin_headers) -> None:
    """Defence in depth: a secret must not be returned even to an admin."""

    monkeypatch.setattr(
        SystemManager,
        "list_configs",
        lambda self: [
            SystemConfigItem(key="ui.theme", value="dark"),
            SystemConfigItem(key="JWT_SECRET_KEY", value="super-secret-value"),
            SystemConfigItem(key="database_url", value="postgresql://user:pw@host/db"),
            SystemConfigItem(key="deepseek_api_key", value="sk-live-should-not-leak"),
            SystemConfigItem(key="courseware.variant_count", value="1"),
        ],
    )

    response = CLIENT.get("/system/configs", headers=admin_headers)
    assert response.status_code == 200

    keys = sorted(item["key"] for item in response.json()["data"])
    assert keys == ["courseware.variant_count", "ui.theme"]
    body = response.text
    for leak in ("super-secret-value", "sk-live-should-not-leak", "postgresql://user:pw@host/db"):
        assert leak not in body, f"secret leaked through the config listing: {leak}"


def test_filter_preserves_non_sensitive_entries() -> None:
    """The filter only removes sensitive-looking keys."""

    items = [
        SystemConfigItem(key="a", value="1"),
        SystemConfigItem(key="api_key", value="x"),
        SystemConfigItem(key="b", value="2"),
    ]
    kept = _filter_configs(items)
    assert [item.key for item in kept] == ["a", "b"]


def test_no_anonymous_internal_caller_depends_on_configs() -> None:
    """Regression guard: no service may reintroduce an anonymous /system/configs call.

    Documented rationale for closing the endpoint: nothing in the running system
    reads it (verified by repository search), so no service-to-service token
    propagation is required.
    """

    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        # Archived acceptance harnesses are evidence, not internal runtime callers.
        if any(part in {".venv", "node_modules", "__pycache__", "artifacts"} for part in path.parts):
            continue
        if path.name == "admin.py" and path.parts[-3:-2] == ("routes",):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "/system/configs" in text and "probe_api" not in path.name and "test_" not in path.name:
            offenders.append(str(path.relative_to(root)))

    assert offenders == [], f"new anonymous callers of /system/configs: {offenders}"
