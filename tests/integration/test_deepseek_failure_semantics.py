"""Deterministic, no-cost failure semantics for the DeepSeek chat path.

These tests never contact DeepSeek. A local HTTP server speaks just enough of
the OpenAI-compatible Chat Completions protocol to exercise the *real* client
and the *real* resource parser:

    LLMFactory -> ChatOpenAI -> local HTTP -> JSON parser

Why not ask a real model to answer with prose, or set a one-second timeout?
Neither is a stable failure test: a model may still obey the JSON contract, and
``LLMFactory`` deliberately clamps the request timeout to ``max(3, configured)``
(``llm_factory.py``). A local server can return non-JSON, 429, 5xx, a delayed
response or a closed connection deterministically, and it spends no tokens.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from common.config import Settings
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.resource_generation import (
    ResourceGenerationError,
    ResourceGenerationService,
)

MIND_MAP_VARIABLES = {
    "subject": "计算机基础",
    "knowledge_point": "二分查找",
    "resource_style": "visual",
    "learner_profile": "无特殊画像要求",
    "context_text": "当前暂无可用参考资料。",
    "grounding_text": "二分查找要求数组有序，每次比较后排除一半区间。",
}

VALID_MIND_MAP = {
    "title": "二分查找思维导图",
    "knowledge_point": "二分查找",
    "root_id": "root",
    "nodes": [
        {"id": "root", "label": "二分查找", "parent_id": None, "level": 0, "detail": "核心"},
        {"id": "n1", "label": "有序数组", "parent_id": "root", "level": 1, "detail": "前提"},
        {"id": "n2", "label": "折半缩小区间", "parent_id": "root", "level": 1, "detail": "方法"},
    ],
    "edges": [
        {"source": "root", "target": "n1", "label": "前提"},
        {"source": "root", "target": "n2", "label": "方法"},
    ],
    "mermaid_source": "",
}


@dataclass
class StubState:
    mode: str = "valid"
    delay_seconds: float = 0.0
    requests: list[dict] = field(default_factory=list)


class _Handler(BaseHTTPRequestHandler):
    state: StubState

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length)
        self.state.requests.append(
            {
                "path": self.path,
                "body": body,
                "at": time.monotonic(),
                "authorization": self.headers.get("authorization", ""),
            }
        )

        mode = self.state.mode
        if mode == "slow":
            time.sleep(self.state.delay_seconds)
        if mode == "disconnect":
            self.connection.close()
            return

        if mode == "http_429":
            self._send(429, {"error": {"message": "rate limited", "type": "rate_limit_error"}})
            return
        if mode == "http_500":
            self._send(500, {"error": {"message": "server error", "type": "server_error"}})
            return
        if mode in {"http_502", "http_503"}:
            self._send(int(mode[-3:]), {"error": {"message": "local upstream unavailable"}})
            return
        if mode == "missing_choices":
            self._send(200, {"id": "local-invalid", "model": "local-stub"})
            return
        if mode == "stream_disconnect":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", "10000")
            self.end_headers()
            self.wfile.write(
                b'data: {"id":"local","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"partial"}}]}\n\n'
            )
            self.wfile.flush()
            self.close_connection = True
            return

        content = (
            json.dumps(VALID_MIND_MAP, ensure_ascii=False)
            if mode == "valid"
            else ""
            if mode == "empty"
            else '{"title":'
            if mode == "malformed_json"
            else "二分查找是一种在有序数组中查找目标的高效方法，先比较中间元素。"
        )
        self._send(
            200,
            {
                "id": "chatcmpl-local-stub",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            },
        )

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args) -> None:  # keep pytest output clean
        return


class _Server:
    def __init__(self, state: StubState) -> None:
        handler = type("Handler", (_Handler,), {"state": state})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> _Server:
        self.thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


def _settings(base_url: str, *, timeout: int = 45) -> Settings:
    return Settings(
        jwt_secret_key="local-stub-not-a-real-secret",
        deepseek_api_key="local-stub-key",
        deepseek_api_base=base_url,
        deepseek_model="deepseek-chat",
        qwen_api_key="",
        qwen_api_base="",
        openai_api_key="",
        llm_request_timeout_seconds=timeout,
        llm_prewarm_enabled=False,
    )


def _service(base_url: str, *, timeout: int = 45) -> ResourceGenerationService:
    service = ResourceGenerationService()
    service.llm_factory = LLMFactory(_settings(base_url, timeout=timeout))
    return service


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch) -> None:
    # Keep the loopback stub out of any proxy configuration inherited by httpx.
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


def test_local_stub_happy_path_parses_structured_json() -> None:
    state = StubState(mode="valid")
    with _Server(state) as server:
        payload = _service(server.base_url)._invoke_structured(
            "mind_map_gen.md", MIND_MAP_VARIABLES
        )

    assert payload["title"] == "二分查找思维导图"
    assert len(payload["nodes"]) == 3
    assert len(state.requests) == 1
    assert state.requests[0]["path"].endswith("/chat/completions")
    assert state.requests[0]["authorization"] == "Bearer local-stub-key"


def test_local_stub_non_json_answer_is_rejected_not_guessed() -> None:
    state = StubState(mode="prose")
    with _Server(state) as server:
        with pytest.raises(ResourceGenerationError) as excinfo:
            _service(server.base_url)._invoke_structured("mind_map_gen.md", MIND_MAP_VARIABLES)

    assert "JSON" in str(excinfo.value)
    assert len(state.requests) == 1


def test_local_stub_http_429_surfaces_without_sdk_retry() -> None:
    state = StubState(mode="http_429")
    started = time.perf_counter()
    with _Server(state) as server:
        with pytest.raises(ResourceGenerationError):
            _service(server.base_url)._invoke_structured("mind_map_gen.md", MIND_MAP_VARIABLES)
    elapsed = time.perf_counter() - started

    assert len(state.requests) == 1, "max_retries=0 must not hide the first 429"
    assert elapsed < 20


def test_local_stub_http_500_surfaces_without_sdk_retry() -> None:
    state = StubState(mode="http_500")
    with _Server(state) as server:
        with pytest.raises(ResourceGenerationError):
            _service(server.base_url)._invoke_structured("mind_map_gen.md", MIND_MAP_VARIABLES)

    assert len(state.requests) == 1


@pytest.mark.parametrize(
    "mode", ["http_502", "http_503", "missing_choices", "empty", "malformed_json"]
)
def test_local_stub_additional_failures_are_not_success(mode: str) -> None:
    state = StubState(mode=mode)
    with _Server(state) as server:
        with pytest.raises(ResourceGenerationError):
            _service(server.base_url)._invoke_structured("mind_map_gen.md", MIND_MAP_VARIABLES)
    assert len(state.requests) == 1


def test_sse_disconnect_does_not_complete_successfully() -> None:
    state = StubState(mode="stream_disconnect")
    chunks = []
    with _Server(state) as server:
        model = LLMFactory(_settings(server.base_url)).build_chat_model()
        with pytest.raises(Exception) as excinfo:
            chunks.extend(model.stream("local stream probe"))
    assert not isinstance(excinfo.value, AssertionError)
    assert len(state.requests) == 1
    assert any("partial" in str(chunk.content) for chunk in chunks)


def test_configured_one_second_timeout_is_clamped_to_three_seconds() -> None:
    """The factory uses max(3, LLM_REQUEST_TIMEOUT_SECONDS), not the raw value."""

    state = StubState(mode="slow", delay_seconds=8.0)
    started = time.perf_counter()
    with _Server(state) as server:
        with pytest.raises(ResourceGenerationError):
            _service(server.base_url, timeout=1)._invoke_structured(
                "mind_map_gen.md", MIND_MAP_VARIABLES
            )
    elapsed = time.perf_counter() - started

    assert len(state.requests) == 1
    assert 2.5 <= elapsed < 7.0, (
        f"a configured 1s request timeout is raised to 3s by LLMFactory; observed {elapsed:.2f}s"
    )


def test_dead_endpoint_fails_instead_of_fabricating() -> None:
    """A closed loopback port is a deterministic stand-in for an unreachable provider."""

    service = ResourceGenerationService()
    service.llm_factory = LLMFactory(_settings("http://127.0.0.1:9/v1", timeout=5))
    started = time.perf_counter()
    with pytest.raises(ResourceGenerationError):
        service._invoke_structured("mind_map_gen.md", MIND_MAP_VARIABLES)
    elapsed = time.perf_counter() - started

    assert elapsed < 60


def test_local_stub_disconnect_surfaces_error() -> None:
    state = StubState(mode="disconnect")
    with _Server(state) as server:
        with pytest.raises(ResourceGenerationError):
            _service(server.base_url)._invoke_structured("mind_map_gen.md", MIND_MAP_VARIABLES)

    assert len(state.requests) == 1


def test_stub_records_only_loopback_target() -> None:
    """Guard against accidentally turning this suite into a paid call."""

    state = StubState(mode="valid")
    with _Server(state) as server:
        service = _service(server.base_url)
        model = service.llm_factory.build_chat_model()
        target = SimpleNamespace(
            base_url=str(getattr(model, "openai_api_base", server.base_url)),
            model=str(getattr(model, "model_name", "deepseek-chat")),
        )
        service._invoke_structured("mind_map_gen.md", MIND_MAP_VARIABLES)

    assert target.base_url.startswith("http://127.0.0.1:")
    assert target.model == "deepseek-chat"
