"""Helpers for selecting, caching, and prewarming an available LLM backend."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from common.ai_errors import AIModelInitializationTimeoutError, AIServiceError, is_timeout_exception
from common.config import Settings
from common.performance import get_current_trace

LOGGER = logging.getLogger(__name__)


class LLMFactory:
    """Build OpenAI-compatible chat models from configured providers."""

    _cache: dict[tuple[Any, ...], Any] = {}
    _cache_lock = threading.Lock()
    _initialization_failures = 0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_chat_model(self, temperature: float = 0.3, model_name: str | None = None):
        """Return a ChatOpenAI-compatible model or raise ImportError/ValueError."""

        from langchain_openai import ChatOpenAI
        timeout = max(3, self.settings.llm_request_timeout_seconds)
        trace = get_current_trace()
        if trace is not None:
            remaining = trace.remaining_seconds()
            if remaining is not None:
                if remaining <= 0:
                    message = "AI request deadline exhausted before model initialization"
                    self._initialization_failures += 1
                    trace.attributes["model_init_attempts"] = 1
                    trace.attributes["model_init_failures"] = 1
                    LOGGER.warning(
                        "llm_model_initialization_failed reason=deadline_exhausted remaining=0"
                    )
                    raise AIModelInitializationTimeoutError(raw_message=message)
        selected_model = model_name or ""
        # An explicitly supplied provider key must win over a different
        # provider's environment fallback. This matters in tests and in a
        # process that keeps several OpenAI-compatible providers configured.
        if self.settings.qwen_api_base and self.settings.qwen_api_key:
            resolved_model = selected_model or self.settings.qwen_model
            return self._get_or_create(
                ChatOpenAI,
                provider="qwen",
                api_key=self.settings.qwen_api_key,
                base_url=self.settings.qwen_api_base,
                model=resolved_model,
                temperature=temperature,
                timeout=timeout,
            )

        if self.settings.deepseek_api_base and self.settings.deepseek_api_key:
            resolved_model = selected_model or self.settings.deepseek_model
            return self._get_or_create(
                ChatOpenAI,
                provider="deepseek",
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_api_base,
                model=resolved_model,
                temperature=temperature,
                timeout=timeout,
            )

        # When only the generic key is configured, retain the historical
        # provider order so existing deployments keep working.
        if self.settings.deepseek_api_base and self.settings.openai_api_key:
            resolved_model = selected_model or self.settings.deepseek_model
            return self._get_or_create(
                ChatOpenAI,
                provider="deepseek-generic-key",
                api_key=self.settings.openai_api_key,
                base_url=self.settings.deepseek_api_base,
                model=resolved_model,
                temperature=temperature,
                timeout=timeout,
            )

        if self.settings.qwen_api_base and self.settings.openai_api_key:
            resolved_model = selected_model or self.settings.qwen_model
            return self._get_or_create(
                ChatOpenAI,
                provider="qwen-generic-key",
                api_key=self.settings.openai_api_key,
                base_url=self.settings.qwen_api_base,
                model=resolved_model,
                temperature=temperature,
                timeout=timeout,
            )

        if self.settings.openai_api_key:
            resolved_model = selected_model or self.settings.openai_model
            return self._get_or_create(
                ChatOpenAI,
                provider="openai",
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=resolved_model,
                temperature=temperature,
                timeout=timeout,
            )

        raise ValueError("No LLM credentials configured.")

    def build_for_task(self, task: str, *, temperature: float = 0.0):
        """Use a light model only when the deployment explicitly configures one."""

        model_name = self.settings.llm_light_model if task in {"rewrite", "classify", "summarize"} else ""
        return self.build_chat_model(temperature=temperature, model_name=model_name or None)

    def prewarm(self) -> dict[str, Any]:
        """Construct configured model clients once during service startup.

        ChatOpenAI is an OpenAI-compatible client, so prewarming intentionally
        does not spend tokens on a probe request. The first user request reuses
        these clients and remains subject to its own inference timeout.
        """

        started = time.perf_counter()
        warmed: list[str] = []
        errors: list[str] = []
        model_names: list[str | None] = [None]
        if self.settings.llm_light_model:
            model_names.append(self.settings.llm_light_model)
        for model_name in model_names:
            try:
                model = self.build_chat_model(model_name=model_name)
                warmed.append(str(model_name or getattr(model, "model_name", "default")))
            except (AIServiceError, ImportError, ValueError) as exc:
                errors.append(str(exc))
                LOGGER.warning("llm_model_prewarm_failed error=%s", str(exc)[:200])
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        LOGGER.info(
            "llm_model_prewarm completed=%s models=%s elapsed_ms=%s failures=%s",
            bool(warmed), ",".join(warmed) or "none", elapsed_ms, len(errors),
        )
        return {"warmed": warmed, "errors": errors, "elapsed_ms": elapsed_ms}

    def _get_or_create(self, chat_openai: Any, **kwargs: Any) -> Any:
        provider = kwargs.pop("provider")
        if os.getenv("AI_PROVIDER_MAX_OUTPUT_TOKENS") is not None:
            kwargs["max_tokens"] = max(1, int(os.environ["AI_PROVIDER_MAX_OUTPUT_TOKENS"]))
        model_name = str(kwargs["model"])
        key = (
            id(chat_openai),
            provider,
            kwargs["api_key"],
            kwargs["base_url"],
            model_name,
            kwargs["temperature"],
            kwargs["timeout"],
            kwargs.get("max_tokens"),
        )
        cached = self._cache.get(key)
        if cached is not None:
            trace = get_current_trace()
            if trace is not None:
                trace.attributes["model_init_attempts"] = 0
                trace.attributes["model_init_failures"] = 0
                trace.attributes["model_init_cold_start"] = False
                trace.attributes["model_init_ready"] = True
            self._record_model(model_name)
            return cached

        started = time.perf_counter()
        lock_started = time.perf_counter()
        created = False
        with self._cache_lock:
            lock_wait_ms = (time.perf_counter() - lock_started) * 1000
            trace = get_current_trace()
            if trace is not None:
                trace.attributes["model_init_lock_wait_ms"] = round(lock_wait_ms, 3)
            cached = self._cache.get(key)
            if cached is None:
                try:
                    # A different request may have held the process-wide
                    # initialization lock long enough to exhaust this request.
                    # Do not start a new constructor after its deadline.
                    if trace is not None:
                        trace.ensure_deadline("model_initialization")
                    from common.model_usage import UsageCallback
                    cached = chat_openai(**kwargs, max_retries=0, stream_usage=True,
                                         callbacks=[UsageCallback(provider, model_name)])
                    self._cache[key] = cached
                    created = True
                except AIServiceError:
                    self._initialization_failures += 1
                    if trace is not None:
                        trace.attributes["model_init_attempts"] = 0
                        trace.attributes["model_init_failures"] = 1
                        trace.attributes["model_init_ready"] = False
                    LOGGER.warning(
                        "llm_model_initialization_failed reason=deadline_exhausted_before_constructor "
                        "provider=%s model=%s lock_wait_ms=%.3f",
                        provider,
                        model_name,
                        lock_wait_ms,
                    )
                    raise
                except Exception as exc:
                    self._initialization_failures += 1
                    if not is_timeout_exception(exc):
                        raise
                    if trace is not None:
                        trace.attributes["model_init_attempts"] = 1
                        trace.attributes["model_init_failures"] = 1
                    LOGGER.exception(
                        "llm_model_initialization_failed provider=%s model=%s elapsed_ms=%.3f",
                        provider,
                        model_name,
                        (time.perf_counter() - started) * 1000,
                    )
                    raise AIModelInitializationTimeoutError(raw_message=str(exc)) from exc

        elapsed_ms = (time.perf_counter() - started) * 1000
        trace = get_current_trace()
        if not created:
            if trace is not None:
                trace.attributes["model_init_attempts"] = 0
                trace.attributes["model_init_failures"] = 0
                trace.attributes["model_init_cold_start"] = False
                trace.attributes["model_init_ready"] = True
            self._record_model(model_name)
            return cached
        if trace is not None:
            # A local model server may spend most of the request budget inside
            # its constructor/load path. Re-check the deadline after creation
            # so this is reported as initialization timeout, not inference timeout.
            try:
                trace.ensure_deadline("model_initialization")
            except AIServiceError:
                self._initialization_failures += 1
                trace.attributes["model_init_failures"] = 1
                trace.attributes["model_init_ready"] = False
                LOGGER.warning(
                    "llm_model_initialization_failed reason=deadline_exhausted provider=%s model=%s elapsed_ms=%.3f",
                    provider,
                    model_name,
                    elapsed_ms,
                )
                raise
            trace.attributes["model_init_attempts"] = 1
            trace.attributes["model_init_failures"] = 0
            trace.add_stage("model_initialization", elapsed_ms)
            trace.attributes["model_init_cold_start"] = True
            trace.attributes["model_init_ready"] = True
        LOGGER.info(
            "llm_model_initialization_ready provider=%s model=%s cold_start=true elapsed_ms=%.3f",
            provider,
            model_name,
            elapsed_ms,
        )
        self._record_model(model_name)
        return cached

    def _record_model(self, model_name: str) -> None:
        trace = get_current_trace()
        if trace is not None:
            trace.model_name = model_name
