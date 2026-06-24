"""Unit tests for provider-aware LLM factory configuration."""

from common.config import Settings
from services.agent_service.app.services.llm_factory import LLMFactory


def test_llm_factory_prefers_deepseek_specific_api_key(monkeypatch):
    """DeepSeek should use its provider-specific key when configured."""

    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)

    factory = LLMFactory(
        Settings(
            jwt_secret_key="test-secret",
            openai_api_key="",
            deepseek_api_key="deepseek-key",
            deepseek_api_base="https://api.deepseek.com/v1",
            deepseek_model="deepseek-chat",
        )
    )

    factory.build_chat_model()

    assert captured["api_key"] == "deepseek-key"
    assert captured["base_url"] == "https://api.deepseek.com/v1"
    assert captured["model"] == "deepseek-chat"


def test_llm_factory_prefers_qwen_specific_api_key(monkeypatch):
    """Qwen should use its provider-specific key when configured."""

    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)

    factory = LLMFactory(
        Settings(
            jwt_secret_key="test-secret",
            openai_api_key="",
            qwen_api_key="qwen-key",
            qwen_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            qwen_model="qwen-plus",
        )
    )

    factory.build_chat_model()

    assert captured["api_key"] == "qwen-key"
    assert captured["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert captured["model"] == "qwen-plus"


def test_llm_factory_raises_without_any_credentials():
    """Missing keys across all providers should surface a clear configuration error."""

    factory = LLMFactory(
        Settings(
            jwt_secret_key="test-secret",
            openai_api_key="",
            qwen_api_key="",
            deepseek_api_key="",
            qwen_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            deepseek_api_base="https://api.deepseek.com/v1",
        )
    )

    try:
        factory.build_chat_model()
    except ValueError as exc:
        assert str(exc) == "No LLM credentials configured."
    else:
        raise AssertionError("Expected ValueError when no provider credentials are configured")
