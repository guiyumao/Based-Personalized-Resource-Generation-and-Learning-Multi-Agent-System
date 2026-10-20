"""Real SDK protocol calls and durable callback metadata; no paid Provider."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common import model_usage
from common.config import Settings
from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.operations import ModelCall, WorkerInstance
from common.performance import performance_trace
from common.worker_heartbeat import WorkerHeartbeat
from scripts.no_cost_mock_provider import MockProvider
from services.agent_service.app.main import app
from services.agent_service.app.services.llm_factory import LLMFactory


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'ledger.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(model_usage, "SessionLocal", factory)
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


def test_real_sdk_invoke_async_stream_are_distinct_and_metadata_survives_parsers(ledger, tmp_path):
    from langchain_core.output_parsers import StrOutputParser
    provider = MockProvider(tmp_path / "protocol.jsonl").start()
    try:
        model = LLMFactory(Settings(openai_api_key="test-only", openai_base_url=provider.base_url, openai_model="requested-test",
            deepseek_api_key="", deepseek_api_base="", qwen_api_key="", qwen_api_base="")).build_chat_model()
        with performance_trace(service_name="test", user_id=21, task_type="qa-fixture"):
            assert (model | StrOutputParser()).invoke("PRIVATE_PROMPT_NOT_STORED")
            assert asyncio.run(model.ainvoke("private-async")).content
            assert list(model.stream("private-stream"))
        with ledger() as db:
            rows = db.query(ModelCall).order_by(ModelCall.started_at).all()
            assert len(rows) == 3
            assert all(row.mode == "TEST" and row.user_id == 21 and row.feature == "qa-fixture" for row in rows)
            assert all(row.status == "SUCCEEDED" for row in rows)
            assert [(row.input_tokens, row.output_tokens) for row in rows[:2]] == [(10, 20), (10, 20)]
            assert rows[0].model == "requested-test" and rows[0].response_model == "no-cost-stub"
            assert rows[2].usage_status == "UNKNOWN" and rows[2].input_tokens is None
            assert "PRIVATE_PROMPT" not in str([vars(row) for row in rows])
    finally:
        provider.close()


def test_zero_unknown_partial_cache_and_failed_call_idempotence(ledger):
    first = str(uuid4())
    model_usage.begin_call(first, "test", "model")
    model_usage.finish_call(first, response={"usage": {"prompt_tokens": 0, "completion_tokens": 0}})
    model_usage.finish_call(first, response={"usage": {"prompt_tokens": 99, "completion_tokens": 99}})
    second = str(uuid4())
    model_usage.begin_call(second, "test", "model")
    model_usage.finish_call(second, error=RuntimeError("Bearer SECRET_CONTENT"))
    third = str(uuid4())
    model_usage.begin_call(third, "test", "model")
    model_usage.finish_call(third, response={"usage": {"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 30}}})
    with ledger() as db:
        assert db.get(ModelCall, first).usage_status == "KNOWN"
        assert db.get(ModelCall, first).input_tokens == 0
        assert db.get(ModelCall, second).input_tokens is None
        assert db.get(ModelCall, second).error_code == "RuntimeError"
        assert db.get(ModelCall, third).cached_input_tokens == 30
        assert db.get(ModelCall, third).usage_status == "PARTIAL"
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    payload = TestClient(app).get("/admin/usage?mode=TEST").json()
    assert payload["summary"]["input_tokens"] is None
    assert payload["summary"]["known_input_subtotal"] == 100
    assert payload["summary"]["output_tokens"] is None
    assert payload["summary"]["calls"] == 3
    assert TestClient(app).get("/admin/usage?mode=LIVE").json()["total"] == 0


def test_zero_call_budget_prevents_sdk_provider_contact(ledger, tmp_path, monkeypatch):
    provider = MockProvider(tmp_path / "zero-budget.jsonl").start()
    monkeypatch.setenv("AI_PROVIDER_DAY_CALL_LIMIT", "0")
    try:
        model = LLMFactory(Settings(openai_api_key="test-only", openai_base_url=provider.base_url,
            deepseek_api_key="", deepseek_api_base="", qwen_api_key="", qwen_api_base="")).build_chat_model()
        with pytest.raises(model_usage.ModelCallBudgetExceeded):
            model.invoke("must not leave process")
        assert not (tmp_path / "zero-budget.jsonl").exists()
        with ledger() as db:
            assert db.query(ModelCall).count() == 0
    finally:
        provider.close()


def test_usage_and_worker_api_deny_nonadmins_and_infer_staleness(ledger):
    client = TestClient(app)
    assert client.get("/admin/usage").status_code == 401
    assert client.get("/admin/workers").status_code == 401
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="student")
    assert client.get("/admin/usage").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
    with WorkerHeartbeat("test", ["knowledge"], interval=1, session_factory=ledger) as worker:
        assert client.get("/admin/workers").json()["items"][0]["status"] == "ONLINE"
        worker.batch(RuntimeError("sensitive"))
        assert client.get("/admin/workers").json()["items"][0]["status"] == "DEGRADED"
        with ledger() as db:
            row = db.get(WorkerInstance, worker.id)
            row.heartbeat_at = datetime.utcnow() - timedelta(seconds=100)
            db.commit()
        assert client.get("/admin/workers").json()["items"][0]["status"] == "STALE"
    assert client.get("/admin/workers").json()["items"][0]["status"] == "STOPPED"


def test_new_topic_generation_does_not_hold_writer_lock_during_provider(ledger,tmp_path,monkeypatch):
    from common.models.learning import User
    from common.schemas.agent import ExerciseGenerationRequest
    from services.agent_service.app.services import exercise_generation
    provider=MockProvider(tmp_path/"new-topic-protocol.jsonl").start()
    settings=Settings(openai_api_key="test-only",openai_base_url=provider.base_url,deepseek_api_key="",deepseek_api_base="",qwen_api_key="",qwen_api_base="")
    monkeypatch.setattr(exercise_generation,"SessionLocal",ledger)
    monkeypatch.setattr(exercise_generation,"get_settings",lambda:settings)
    with ledger() as db:
        db.add(User(id=21,username="new-topic-user",password_hash="unused"))
        db.commit()
    try:
        result=exercise_generation.ExerciseGenerationService().generate_exercises(ExerciseGenerationRequest(user_id=21,knowledge_point="TCP",exercise_count=3,learner_profile={"history_disabled":True}))
        assert len(result["exercises"])==3
        assert result["audit_reason"]!="deterministic_fallback"
        with ledger() as db:
            assert db.query(ModelCall).count()>=1
    finally:
        provider.close()
