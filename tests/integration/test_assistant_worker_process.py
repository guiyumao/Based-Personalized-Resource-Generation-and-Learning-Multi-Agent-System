"""Exercise the durable queue from independent Python Worker processes."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from common.db.base import Base
from common.models.learning import AssistantAgentExecution, AssistantTask, ChatMessage, ChatSession, User


def test_independent_workers_consume_persisted_task_once(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'worker.sqlite').as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="worker_student", password_hash="test", role="student")
        db.add(user)
        db.flush()
        session = ChatSession(user_id=user.id, title="durable", subject="test")
        db.add(session)
        db.flush()
        task = AssistantTask(user_id=user.id, session_id=session.id, client_request_id="process-worker-request",
                             task_type="profile", status="PENDING", request_json={}, result_json={})
        db.add(task)
        db.commit()
        task_id, session_id = task.id, session.id
    env = {**os.environ, "DATABASE_URL": database_url, "ASSISTANT_TASK_EXECUTION_MODE": "worker"}
    command = [sys.executable, "-m", "services.agent_service.app.services.assistant_worker", "--once"]
    processes = []
    try:
        for _index in range(2):
            processes.append(subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2], env=env,
                                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace"))
        for process in processes:
            output, _ = process.communicate(timeout=90)
            assert process.returncode == 0, output[-4000:]
        with Session(engine) as db:
            result = db.get(AssistantTask, task_id)
            assert result.status == "SUCCEEDED"
            assert result.result_json["evidence"]["answer_records"] == 0
            assert db.query(ChatMessage).filter(ChatMessage.session_id == session_id, ChatMessage.role == "assistant").count() == 1
            assert db.query(AssistantAgentExecution).filter(AssistantAgentExecution.task_id == task_id).count() == 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()
        engine.dispose()


def test_killed_worker_read_only_task_recovers_in_another_process(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'crash-recovery.sqlite').as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="crash_student", password_hash="test", role="student")
        db.add(user)
        db.flush()
        session = ChatSession(user_id=user.id, title="crash", subject="test")
        db.add(session)
        db.flush()
        task = AssistantTask(user_id=user.id, session_id=session.id, client_request_id="crash-worker-request",
                             task_type="profile", status="PENDING", request_json={}, result_json={})
        db.add(task)
        db.commit()
        task_id, session_id = task.id, session.id
    env = {**os.environ, "DATABASE_URL": database_url, "ASSISTANT_TASK_EXECUTION_MODE": "worker",
           "ASSISTANT_SAFE_RETRY_BACKOFF_SECONDS": "0", "ASSISTANT_SAFE_RETRY_LIMIT": "2"}
    script = """
import sys
from services.agent_service.app.services import assistant_tasks
def block(*args):
    print('WORKER_CLAIMED', flush=True)
    sys.stdin.read()
    return {'content': 'unexpected old worker', 'cards': [], 'sources': []}
assistant_tasks._profile_result = block
assistant_tasks.execute_task(int(sys.argv[1]))
"""
    root = Path(__file__).resolve().parents[2]
    process = subprocess.Popen([sys.executable, "-c", script, str(task_id)], cwd=root, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        def wait_for_claim():
            for line in process.stdout:
                if "WORKER_CLAIMED" in line:
                    return True
            return False

        assert pool.submit(wait_for_claim).result(timeout=45), "worker exited before claiming"
        process.kill()
        process.communicate(timeout=15)
        with Session(engine) as db:
            task = db.get(AssistantTask, task_id)
            assert task.status == "RUNNING"
            assert task.execution_attempt == 1
            assert task.worker_id and task.heartbeat_at
            # Move persisted lease time deterministically; no 45 second sleep.
            task.heartbeat_at = datetime.utcnow() - timedelta(minutes=2)
            db.commit()
        recovered = subprocess.run(
            [sys.executable, "-m", "services.agent_service.app.services.assistant_worker", "--once"],
            cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        assert recovered.returncode == 0, recovered.stdout[-2000:] + recovered.stderr[-2000:]
        with Session(engine) as db:
            task = db.get(AssistantTask, task_id)
            assert task.status == "SUCCEEDED"
            assert task.execution_attempt == 2
            assert task.result_json["content"] != "unexpected old worker"
            assert db.query(ChatMessage).filter_by(session_id=session_id, role="assistant").count() == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=15)
        pool.shutdown(wait=True)
        engine.dispose()
