from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from services.agent_service.app.services import deepseek_search


@pytest.fixture(autouse=True)
def public_dns_for_transport_tests(monkeypatch):
    monkeypatch.setattr(deepseek_search, "_resolve_public_host", lambda _host: True)


def test_search_and_fetch_use_official_endpoints(monkeypatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), request.headers["Authorization"]))
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"results": [{"title": "Lesson", "url": "https://example.edu", "snippet": "Intro"}]})
        return httpx.Response(200, json={"title": "Lesson", "content": "# Lesson"})

    transport = httpx.MockTransport(handler)
    client_class = httpx.Client
    monkeypatch.setattr(deepseek_search, "get_settings", lambda: SimpleNamespace(deepseek_api_key="test-key"))
    monkeypatch.setattr(deepseek_search.httpx, "Client", lambda **kwargs: client_class(transport=transport, **kwargs))
    assert deepseek_search.search_sources("Python")[0]["summary"] == "Intro"
    assert deepseek_search.fetch_source("https://example.edu")["content"] == "# Lesson"
    assert calls == [
        ("https://api.deepseek.com/v1/tools/search", "Bearer test-key"),
        ("https://api.deepseek.com/v1/tools/fetch", "Bearer test-key"),
    ]


def test_search_root_can_be_overridden_only_for_reviewed_gateway(monkeypatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(deepseek_search, "_ROOT", "http://127.0.0.1:45678")
    monkeypatch.setattr(deepseek_search, "get_settings", lambda: SimpleNamespace(deepseek_api_key="test-key"))
    client_class = httpx.Client
    monkeypatch.setattr(
        deepseek_search.httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )

    assert deepseek_search.search_sources("Python") == []
    assert calls == ["http://127.0.0.1:45678/v1/tools/search"]


def test_search_requires_deepseek_key(monkeypatch) -> None:
    monkeypatch.setattr(deepseek_search, "get_settings", lambda: SimpleNamespace(deepseek_api_key=""))
    with pytest.raises(deepseek_search.DeepSeekSearchUnavailable):
        deepseek_search.search_sources("Python")


def test_rate_limited_search_retries_once(monkeypatch) -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": {"code": "rate_limit"}})
        return httpx.Response(200, json={"results": []})

    client_class = httpx.Client
    monkeypatch.setattr(deepseek_search, "get_settings", lambda: SimpleNamespace(deepseek_api_key="test-key"))
    monkeypatch.setattr(deepseek_search.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(deepseek_search.httpx, "Client", lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs))
    assert deepseek_search.search_sources("Python") == []
    assert attempts == 2


@pytest.mark.parametrize("url", ["http://localhost./x", "http://127.1/x", "http://2130706433", "http://[::1]/", "http://service.internal", "http://example.org:bad"])
def test_unsafe_source_urls_are_rejected(url):
    assert not deepseek_search._public_url(url)


def test_long_fetch_timeout_is_45_seconds_and_retry_is_bounded(monkeypatch):
    attempts, timeouts = [], []
    def handler(_request):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("injected timeout")
        return httpx.Response(200, json={"content": "long source " * 6000})
    client_class = httpx.Client
    def client(**kwargs):
        timeouts.append(kwargs["timeout"])
        return client_class(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(deepseek_search, "get_settings", lambda: SimpleNamespace(deepseek_api_key="test"))
    monkeypatch.setattr(deepseek_search.httpx, "Client", client)
    monkeypatch.setattr(deepseek_search.time, "sleep", lambda _: None)
    result = deepseek_search.fetch_source("https://example.edu/course")
    assert len(result["content"]) == 50000 and result["truncated"]
    assert timeouts == [45.0, 45.0]
