"""Drain durable knowledge tasks: python -m services.agent_service.app.services.knowledge_worker."""

from __future__ import annotations

import argparse
import logging
import signal
import threading

from common.db.bootstrap import ensure_database_schema
from common.logging.setup import configure_logging
from common.worker_heartbeat import WorkerHeartbeat
from services.agent_service.app.services.knowledge_tasks import (
    expire_interrupted_tasks,
    run_pending_tasks,
)
from services.agent_service.app.services.knowledge_maintenance import dispatch_due_plans

LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run persisted knowledge-base tasks")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 20 or not .5 <= args.poll_interval <= 60:
        parser.error("batch-size must be 1–20 and poll-interval must be 0.5–60 seconds")
    configure_logging("knowledge-worker")
    ensure_database_schema()
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_args: stop.set())
    LOGGER.info("knowledge_worker_started batch_size=%s", args.batch_size)
    with WorkerHeartbeat("knowledge", ["knowledge", "maintenance"]) as worker:
        while not stop.is_set():
            try:
                dispatch_due_plans()
                expire_interrupted_tasks()
                run_pending_tasks(args.batch_size)
                worker.batch()
            except Exception as exc:
                worker.batch(exc)
                LOGGER.exception("knowledge_worker_batch_failed")
                if args.once:
                    raise
            if args.once:
                break
            stop.wait(args.poll_interval)
    LOGGER.info("knowledge_worker_stopped")


if __name__ == "__main__":
    main()
