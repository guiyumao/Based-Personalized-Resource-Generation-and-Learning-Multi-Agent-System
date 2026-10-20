"""Lightweight request tracing for AI and retrieval workloads.

The module intentionally uses process-local state and structured logs.  It adds
no external infrastructure and can later be exported to a metrics backend
without changing service code.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from common.ai_errors import (
    AIInferenceTimeoutError,
    AIModelInitializationTimeoutError,
    AIServiceError,
    is_timeout_exception,
)

LOGGER = logging.getLogger("ai.performance")
_TRACE_FILE_LOCK = threading.Lock()

_STAGE_FIELDS = {
    "retrieval",
    "query_rewrite",
    "embedding",
    "vector_search",
    "rerank",
    "generation",
    "model_initialization",
    "learner_profile",
    "knowledge_graph",
    "audit",
    "retry",
    "persistence",
}


def _safe_user_id(value: Any) -> str | None:
    """Return a non-secret user identifier suitable for logs."""

    if value is None:
        return None
    text = str(value).strip()
    return text[:64] if text else None


@dataclass
class PerformanceTrace:
    """Accumulate stage durations and request-level AI metadata."""

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str | None = None
    task_type: str = "unknown"
    service_name: str = "unknown"
    started_at: float = field(default_factory=time.perf_counter)
    stage_ms: dict[str, float] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    retrieved_chunks: int = 0
    context_chars: int = 0
    context_tokens: int = 0
    model_name: str = ""
    cache_hit: bool = False
    cache_type: str = "none"
    audit_retry_count: int = 0
    retry_count: int = 0
    retry_stage: str = ""
    retry_reason: str = ""
    status_code: int = 0
    token_estimate: bool = False
    deadline_seconds: float | None = None
    retry_budget: int = 2
    attributes: dict[str, Any] = field(default_factory=dict)

    def set_context(
        self,
        *,
        user_id: Any | None = None,
        task_type: str | None = None,
        **attributes: Any,
    ) -> None:
        if user_id is not None:
            self.user_id = _safe_user_id(user_id)
        if task_type:
            self.task_type = task_type[:80]
        deadline = attributes.pop("deadline_seconds", None)
        retry_budget = attributes.pop("retry_budget", None)
        if deadline is not None:
            self.deadline_seconds = max(1.0, float(deadline))
        if retry_budget is not None:
            self.retry_budget = max(0, int(retry_budget))
        self.attributes.update({key: value for key, value in attributes.items() if value is not None})

    def remaining_seconds(self) -> float | None:
        if self.deadline_seconds is None:
            return None
        elapsed = time.perf_counter() - self.started_at
        return max(0.0, self.deadline_seconds - elapsed)

    def ensure_deadline(self, stage: str) -> None:
        remaining = self.remaining_seconds()
        if remaining is not None and remaining <= 0:
            message = f"AI request deadline exhausted before {stage}"
            if stage == "model_initialization":
                raise AIModelInitializationTimeoutError(raw_message=message)
            raise AIInferenceTimeoutError(raw_message=message)

    def can_retry(self) -> bool:
        return self.retry_count < self.retry_budget

    def add_stage(self, stage: str, elapsed_ms: float) -> None:
        self.stage_ms[stage] = round(self.stage_ms.get(stage, 0.0) + elapsed_ms, 3)

    @contextmanager
    def stage(self, stage: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.add_stage(stage, (time.perf_counter() - started) * 1000)

    def record_context(self, value: str, *, exact_tokens: int | None = None) -> None:
        self.context_chars = max(self.context_chars, len(value))
        if exact_tokens is not None:
            self.context_tokens = max(self.context_tokens, exact_tokens)
            return
        self.context_tokens = max(self.context_tokens, max(1, len(value) // 3)) if value else 0
        self.token_estimate = bool(value)

    def record_retrieval(self, chunks: int, *, cache_hit: bool = False, cache_type: str = "none") -> None:
        self.retrieved_chunks = max(self.retrieved_chunks, chunks)
        self.cache_hit = self.cache_hit or cache_hit
        if cache_hit:
            self.cache_type = cache_type

    def record_model_response(self, response: Any, *, model_name: str = "") -> None:
        """Extract token counts from common LangChain/OpenAI response shapes."""

        self.model_name = model_name or self.model_name
        usage = getattr(response, "usage_metadata", None) or {}
        response_metadata = getattr(response, "response_metadata", None) or {}
        token_usage = response_metadata.get("token_usage", {}) if isinstance(response_metadata, dict) else {}
        if not isinstance(usage, dict):
            usage = {}
        self.prompt_tokens += int(usage.get("input_tokens") or token_usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("output_tokens") or token_usage.get("completion_tokens") or 0)

    def record_estimated_usage(self, prompt: Any, response: Any) -> None:
        """Record conservative estimates when a parser removed provider metadata."""

        try:
            prompt_text = json.dumps(prompt, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            prompt_text = str(prompt)
        response_text = getattr(response, "content", response)
        self.prompt_tokens += max(1, len(prompt_text) // 3) if prompt_text else 0
        self.completion_tokens += max(1, len(str(response_text)) // 3) if response_text else 0
        self.token_estimate = True

    def record_retry(self, *, stage: str, reason: str, audit: bool = False) -> None:
        self.retry_count += 1
        self.retry_stage = stage[:80]
        self.retry_reason = reason[:200]
        if audit:
            self.audit_retry_count += 1

    def to_dict(self) -> dict[str, Any]:
        total_ms = round((time.perf_counter() - self.started_at) * 1000, 3)
        measured_ms = sum(self.stage_ms.get(stage, 0.0) for stage in _STAGE_FIELDS)
        payload: dict[str, Any] = {
            "event": "ai_performance_trace",
            "service": self.service_name,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "task_type": self.task_type,
            **{f"{stage}_ms": round(self.stage_ms.get(stage, 0.0), 3) for stage in sorted(_STAGE_FIELDS)},
            "total_ms": total_ms,
            "other_ms": round(max(0.0, total_ms - measured_ms), 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "retrieved_chunks": self.retrieved_chunks,
            "context_chars": self.context_chars,
            "context_tokens": self.context_tokens,
            "token_estimate": self.token_estimate,
            "model_name": self.model_name,
            "cache_hit": self.cache_hit,
            "cache_type": self.cache_type,
            "audit_retry_count": self.audit_retry_count,
            "retry_count": self.retry_count,
            "retry_stage": self.retry_stage,
            "retry_reason": self.retry_reason,
            "status_code": self.status_code,
            "deadline_seconds": self.deadline_seconds,
            "remaining_ms": (
                round(self.remaining_seconds() * 1000, 3)
                if self.remaining_seconds() is not None
                else None
            ),
        }
        payload.update(self.attributes)
        return payload


def _append_jsonl(payload: dict[str, Any]) -> None:
    """Persist one trace line locally when a log path is configured."""

    configured = os.getenv("AI_PERFORMANCE_LOG_PATH", "./logs/ai-performance.jsonl").strip()
    if not configured:
        return
    path = Path(configured)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with _TRACE_FILE_LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
    except OSError:
        LOGGER.exception("unable_to_write_performance_trace path=%s", path)


_current_trace: ContextVar[PerformanceTrace | None] = ContextVar("current_performance_trace", default=None)


def get_current_trace() -> PerformanceTrace | None:
    return _current_trace.get()


def set_trace_context(*, user_id: Any | None = None, task_type: str | None = None, **attributes: Any) -> None:
    trace = get_current_trace()
    if trace is not None:
        trace.set_context(user_id=user_id, task_type=task_type, **attributes)


def traced_invoke(
    runnable: Any,
    payload: Any,
    *,
    stage: str = "generation",
    model_name: str = "",
    **kwargs: Any,
) -> Any:
    """Invoke a LangChain model/chain while collecting duration and usage."""

    trace = get_current_trace()
    if trace is not None:
        trace.ensure_deadline(stage)
    started = time.perf_counter()
    try:
        result = runnable.invoke(payload, **kwargs)
    except AIServiceError:
        raise
    except Exception as exc:
        if is_timeout_exception(exc):
            raise AIInferenceTimeoutError(raw_message=str(exc)) from exc
        raise
    finally:
        if trace is not None:
            trace.add_stage(stage, (time.perf_counter() - started) * 1000)
    if trace is not None:
        tokens_before = trace.prompt_tokens + trace.completion_tokens
        trace.record_model_response(result, model_name=model_name)
        if trace.prompt_tokens + trace.completion_tokens == tokens_before:
            trace.record_estimated_usage(payload, result)
    return result


@contextmanager
def performance_trace(
    *,
    service_name: str,
    request_id: str | None = None,
    trace_id: str | None = None,
    user_id: Any | None = None,
    task_type: str = "unknown",
) -> Iterator[PerformanceTrace]:
    trace = PerformanceTrace(
        request_id=request_id or uuid.uuid4().hex,
        trace_id=trace_id or uuid.uuid4().hex,
        user_id=_safe_user_id(user_id),
        task_type=task_type,
        service_name=service_name,
    )
    token: Token[PerformanceTrace | None] = _current_trace.set(trace)
    try:
        yield trace
    finally:
        _current_trace.reset(token)


class PerformanceTraceMiddleware(BaseHTTPMiddleware):
    """Create one trace for every HTTP request and emit one JSON log line."""

    def __init__(self, app: Any, service_name: str) -> None:
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        trace_id = request.headers.get("x-trace-id") or request_id
        with performance_trace(
            service_name=self.service_name,
            request_id=request_id,
            trace_id=trace_id,
            task_type=f"{request.method} {request.url.path}",
        ) as trace:
            try:
                response = await call_next(request)
                trace.status_code = response.status_code
            except Exception:
                trace.status_code = 500
                LOGGER.exception("request_failed trace_id=%s request_id=%s", trace_id, request_id)
                raise
            finally:
                payload = trace.to_dict()
                LOGGER.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                _append_jsonl(payload)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        server_timing = [
            f"{name};dur={duration:.1f}" for name, duration in trace.stage_ms.items() if duration > 0
        ]
        if server_timing:
            response.headers["Server-Timing"] = ", ".join(server_timing)
        return response
