"""Helpers for selecting an available LLM backend."""

from __future__ import annotations

from common.config import Settings


class LLMFactory:
    """Build OpenAI-compatible chat models from configured providers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_chat_model(self, temperature: float = 0.3, model_name: str | None = None):
        """Return a ChatOpenAI-compatible model or raise ImportError/ValueError."""

        from langchain_openai import ChatOpenAI
        timeout = max(3, self.settings.llm_request_timeout_seconds)
        selected_model = model_name or ""
        deepseek_api_key = self.settings.deepseek_api_key or self.settings.openai_api_key
        qwen_api_key = self.settings.qwen_api_key or self.settings.openai_api_key

        if self.settings.deepseek_api_base and deepseek_api_key:
            return ChatOpenAI(
                api_key=deepseek_api_key,
                base_url=self.settings.deepseek_api_base,
                model=selected_model or self.settings.deepseek_model,
                temperature=temperature,
                timeout=timeout,
                max_retries=0,
            )

        if self.settings.qwen_api_base and qwen_api_key:
            return ChatOpenAI(
                api_key=qwen_api_key,
                base_url=self.settings.qwen_api_base,
                model=selected_model or self.settings.qwen_model,
                temperature=temperature,
                timeout=timeout,
                max_retries=0,
            )

        if self.settings.openai_api_key:
            return ChatOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=selected_model or self.settings.openai_model,
                temperature=temperature,
                timeout=timeout,
                max_retries=0,
            )

        raise ValueError("No LLM credentials configured.")
