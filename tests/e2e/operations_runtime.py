"""Real SDK accounting, idle Worker process and existing real browser flow."""
import asyncio
import json
import os
import runpy
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
os.environ["OPERATIONS_LEDGER_TEST"] = "1"
os.environ["LOCAL_ARTIFACT_TEST"] = "1"
original = subprocess.run


def with_operations(args, *positional, **kwargs):
    if args != ["node", "tests/e2e/run-learning-workspace.mjs"]:
        return original(args, *positional, **kwargs)
    from common.config import Settings
    from common.db.session import SessionLocal
    from common.models.operations import ModelCall, WorkerInstance
    from common.performance import performance_trace
    from scripts.no_cost_mock_provider import MockProvider
    from services.agent_service.app.services.llm_factory import LLMFactory
    root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
    provider = MockProvider(root / "local-provider.jsonl").start()
    worker_id = None
    with (root / "idle-worker.log").open("w", encoding="utf-8") as log:
        worker = subprocess.Popen([sys.executable, "-m", "services.agent_service.app.services.knowledge_worker", "--poll-interval", "0.5"], stdout=log, stderr=subprocess.STDOUT)
        try:
            model = LLMFactory(Settings(openai_api_key="local-test", openai_base_url=provider.base_url,
                openai_model="requested-test", qwen_api_key="", qwen_api_base="", deepseek_api_key="", deepseek_api_base="")).build_chat_model()
            with performance_trace(service_name="test", user_id=1, task_type="e2e-protocol"):
                model.invoke("protocol fixture")
                asyncio.run(model.ainvoke("async protocol fixture"))
                list(model.stream("stream fixture without usage"))
            for _ in range(100):
                with SessionLocal() as db:
                    registered = db.query(WorkerInstance).first()
                    if registered:
                        first_heartbeat, worker_id = registered.heartbeat_at, registered.id
                        break
                assert worker.poll() is None
                time.sleep(.2)
            else:
                raise RuntimeError("Worker never registered")
            result = original(args, *positional, **kwargs)
            with SessionLocal() as db:
                assert db.get(WorkerInstance, worker_id).heartbeat_at > first_heartbeat
                assert db.query(ModelCall).filter_by(mode="TEST").count() == 3
            return result
        finally:
            worker.terminate()
            worker.wait(timeout=15)
            provider.close()
            if worker_id:
                time.sleep(16)
                with SessionLocal() as db:
                    row = db.get(WorkerInstance, worker_id)
                    assert row.status == "RUNNING"
                    assert (datetime.utcnow()-row.heartbeat_at).total_seconds() > 15
                    (root / "operations-process-result.json").write_text(json.dumps({"passed": True, "idle_heartbeat_advanced": True, "hard_exit_heartbeat_stale": True, "test_model_calls": 3, "real_paid_calls": 0}), encoding="utf-8")


subprocess.run = with_operations
try:
    runpy.run_path("tests/e2e/learning_workspace_runtime.py", run_name="__main__")
finally:
    subprocess.run = original
