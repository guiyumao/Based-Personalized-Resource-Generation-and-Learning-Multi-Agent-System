"""Regression tests for AI initialization and inference timeout handling."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from common.ai_errors import AIInferenceTimeoutError, AIModelInitializationTimeoutError
from common.config import Settings
from common.performance import PerformanceTrace
from common.schemas.agent import QARequest
from services.agent_service.app.api.routes import qa
from services.agent_service.app.services.llm_factory import LLMFactory


def test_deadline_errors_are_distinguished_by_stage() -> None:
    trace = PerformanceTrace()
    trace.set_context(deadline_seconds=1)
    trace.started_at = time.perf_counter() - 2

    with pytest.raises(AIModelInitializationTimeoutError):
        trace.ensure_deadline("model_initialization")
    with pytest.raises(AIInferenceTimeoutError):
        trace.ensure_deadline("generation")


def test_llm_factory_reuses_same_provider_model_client(monkeypatch) -> None:
    created = 0

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            nonlocal created
            created += 1
            self.model_name = kwargs["model"]

    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)
    factory = LLMFactory(
        Settings(
            jwt_secret_key="test-secret",
            openai_api_key="openai-key",
            openai_base_url="https://example.test/v1",
            openai_model="test-model",
        )
    )

    first = factory.build_chat_model()
    second = factory.build_chat_model()

    assert first is second
    assert created == 1


def test_qa_route_maps_model_initialization_timeout_to_student_safe_error(monkeypatch) -> None:
    captured_agents = []

    class FakeCoordinatorWorkflow:
        def __init__(self, db=None):
            self.db = db

        def run(self, request):
            captured_agents.extend(request.payload["force_agents"])
            return {
                "outputs": {
                    "qa_agent": {
                        "status": "failed",
                        "error_code": "AI_MODEL_INITIALIZATION_TIMEOUT",
                        "error": "AI request deadline exhausted before model initialization",
                    }
                }
            }

    monkeypatch.setattr(qa, "CoordinatorWorkflow", FakeCoordinatorWorkflow)

    with pytest.raises(HTTPException) as raised:
        qa.analyze_question(
            QARequest(
                student_id="1",
                subject="Python",
                grade="freshman",
                question="解释循环",
            ),
            db=object(),
            current_user=SimpleNamespace(id=1, role="student"),
        )

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "code": "AI_MODEL_INITIALIZATION_TIMEOUT",
        "message": "AI助教正在加载中，请稍后重试",
    }
    assert not raised.value.headers or raised.value.headers.get("Retry-After") is None
    assert captured_agents == ["learner_profiling_agent", "qa_agent"]
