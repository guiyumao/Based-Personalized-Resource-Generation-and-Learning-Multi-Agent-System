from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from common.dependencies import get_current_user
from services.agent_service.app.api.routes import learning
from services.agent_service.app.main import app


def test_knowledge_base_management_requires_authentication() -> None:
    client = TestClient(app)

    assert client.get("/knowledge-base/status").status_code == 401
    assert client.get("/knowledge-base/sources").status_code == 401
    assert client.post("/knowledge-base/reindex", json={}).status_code == 401
    assert client.post("/knowledge-base/sources/crawl", json={}).status_code == 401


def test_admin_can_run_bounded_management_operations(monkeypatch) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    monkeypatch.setattr(
        learning,
        "reindex_knowledge_base",
        lambda **kwargs: {"ok": True, "request": kwargs},
    )
    monkeypatch.setattr(
        learning,
        "crawl_knowledge_sources",
        lambda **kwargs: {"ok": True, "request": kwargs},
    )
    client = TestClient(app)
    try:
        reindex_response = client.post(
            "/knowledge-base/reindex",
            json={"subject": "python", "force": False},
        )
        crawl_response = client.post(
            "/knowledge-base/sources/crawl",
            json={"topics": ["MIT算法导论"], "reindex": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert reindex_response.status_code == 200
    assert reindex_response.json()["request"]["subject"] == "python"
    assert crawl_response.status_code == 200
    assert crawl_response.json()["request"]["topics"] == ["MIT算法导论"]


def test_search_rejects_unknown_retrieval_mode() -> None:
    response = TestClient(app).get(
        "/knowledge-base/search",
        params={"q": "算法", "retrieval_mode": "unknown"},
    )
    assert response.status_code == 422
