"""Kill a real worker during an injected slow read and resume on another process."""

import os
import subprocess
import sys
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.models.learning import KnowledgeBuildTask, User
from services.agent_service.app.services import knowledge_tasks


def test_worker_death_requeues_safe_work_and_fences_old_owner(tmp_path, monkeypatch):
    database = tmp_path / "worker-recovery.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(knowledge_tasks, "SessionLocal", factory)
    with factory() as db:
        db.add(User(id=1, username="recovery-admin", password_hash="unused", role="admin")); db.commit()
        task = knowledge_tasks.create_task(db, actor_user_id=1, client_request_id="death", operation_type="KNOWLEDGE_HEALTH_CHECK")
        task_id = task.id
    environment = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}",
                   "KNOWLEDGE_RUNTIME_ROOT": str(tmp_path), "CHROMA_MODE": "persistent",
                   "CHROMA_PERSIST_DIRECTORY": str(tmp_path / "chroma"), "PYTHONIOENCODING": "utf-8"}
    code = "from services.agent_service.app.services import knowledge_tasks as k; import time,sys\ndef slow():\n print('claimed',flush=True)\n time.sleep(60)\n return {}\nk.knowledge_base_status=slow\nk.execute_task(int(sys.argv[1]))"
    owner = subprocess.Popen([sys.executable, "-c", code, str(task_id)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert owner.stdout.readline().strip() == "claimed"
        with factory() as db:
            claimed = db.get(KnowledgeBuildTask, task_id)
            old_worker = claimed.worker_id
            assert claimed.status == "RUNNING" and claimed.execution_attempt == 1
        owner.terminate(); owner.wait(timeout=10)
        with factory() as db:
            item = db.get(KnowledgeBuildTask, task_id)
            item.lease_expires_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
        assert knowledge_tasks.expire_interrupted_tasks() == 1
        assert not knowledge_tasks._finish(task_id, old_worker, 1, status="COMPLETED", result_json={"stale": True})
        with factory() as db:
            db.get(KnowledgeBuildTask, task_id).next_attempt_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
        recovered = subprocess.run([sys.executable, "-m", "services.agent_service.app.services.knowledge_worker", "--once"],
                                   env=environment, capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert recovered.returncode == 0, recovered.stderr[-1500:]
        with factory() as db:
            completed = db.get(KnowledgeBuildTask, task_id)
            assert completed.status == "COMPLETED"
            assert completed.execution_attempt == 2
            assert "stale" not in completed.result_json
    finally:
        if owner.poll() is None:
            owner.kill(); owner.wait(timeout=10)
        engine.dispose()
