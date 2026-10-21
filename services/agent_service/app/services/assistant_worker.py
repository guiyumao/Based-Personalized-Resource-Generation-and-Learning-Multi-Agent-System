"""Drain durable assistant tasks without tying execution to an HTTP process.

Run with ASSISTANT_TASK_EXECUTION_MODE=worker in both API and Worker processes:
python -m services.agent_service.app.services.assistant_worker
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from datetime import datetime

from sqlalchemy import or_

from common.db.bootstrap import ensure_database_schema
from common.logging.setup import configure_logging
from common.models.learning import AssistantTask
from common.worker_heartbeat import WorkerHeartbeat
from services.agent_service.app.services import assistant_tasks
from services.agent_service.app.services import knowledge_tasks
from services.agent_service.app.services.knowledge_maintenance import dispatch_due_plans

LOGGER = logging.getLogger(__name__)


def run_pending_tasks(batch_size: int = 1) -> int:
    """Read persisted queue entries; execute_task atomically claims each one."""
    if not 1 <= batch_size <= 20:
        raise ValueError("batch_size must be between 1 and 20")
    with assistant_tasks.SessionLocal() as db:
        assistant_tasks.expire_stale_tasks(db)
        task_ids = [row.id for row in db.query(AssistantTask.id).filter(
            AssistantTask.status == "PENDING",
            or_(AssistantTask.next_attempt_at.is_(None), AssistantTask.next_attempt_at <= datetime.utcnow()),
        ).order_by(AssistantTask.id).limit(batch_size).all()]
    for task_id in task_ids:
        assistant_tasks.execute_task(task_id)
    return len(task_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run persisted XiaoZhi learning tasks")
    parser.add_argument("--skip-schema-bootstrap", action="store_true", help="Use an already audited runtime without creating unrelated schema")
    parser.add_argument("--once", action="store_true", help="Drain one batch, then exit")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 20 or not .5 <= args.poll_interval <= 60:
        parser.error("batch-size must be 1–20 and poll-interval must be 0.5–60 seconds")
    if assistant_tasks.task_execution_mode() != "worker":
        parser.error("Set ASSISTANT_TASK_EXECUTION_MODE=worker in the API and Worker environments")
    configure_logging("assistant-worker")
    if not args.skip_schema_bootstrap:
        ensure_database_schema()
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_args: stop.set())
    LOGGER.info("assistant_worker_started batch_size=%s", args.batch_size)
    with WorkerHeartbeat("combined", ["assistant", "knowledge", "maintenance"]) as worker:
        while not stop.is_set():
            try:
                count = run_pending_tasks(args.batch_size)
                dispatch_due_plans()
                knowledge_tasks.expire_interrupted_tasks()
                knowledge_count = knowledge_tasks.run_pending_tasks(args.batch_size)
                worker.batch()
                if count:
                    LOGGER.info("assistant_worker_batch candidates=%s", count)
                if knowledge_count:
                    LOGGER.info("knowledge_worker_batch candidates=%s", knowledge_count)
            except Exception as exc:
                worker.batch(exc)
                LOGGER.exception("assistant_worker_batch_failed")
                if args.once:
                    raise
            if args.once:
                break
            stop.wait(args.poll_interval)
    LOGGER.info("assistant_worker_stopped")


if __name__ == "__main__":
    main()
