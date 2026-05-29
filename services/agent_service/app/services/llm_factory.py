"""Helpers for selecting an available LLM backend."""

from __future__ import annotations

from common.config import Settings


class LLMFactory:
    """Build OpenAI-compatible chat models from configured providers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_chat_model(self, temperature: float = 0.3):
        """Return a ChatOpenAI-compatible model or raise ImportError/ValueError."""

        from langchain_openai import ChatOpenAI
        timeout = max(3, self.settings.llm_request_timeout_seconds)

        if self.settings.deepseek_api_base and self.settings.openai_api_key:
            return ChatOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.deepseek_api_base,
                model=self.settings.deepseek_model,
                temperature=temperature,
                timeout=timeout,
                max_retries=0,
            )

        if self.settings.qwen_api_base and self.settings.openai_api_key:
            return ChatOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.qwen_api_base,
                model=self.settings.qwen_model,
                temperature=temperature,
                timeout=timeout,
                max_retries=0,
            )

        if self.settings.openai_api_key:
            return ChatOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                temperature=temperature,
                timeout=timeout,
                max_retries=0,
            )

        raise ValueError("No LLM credentials configured.")
