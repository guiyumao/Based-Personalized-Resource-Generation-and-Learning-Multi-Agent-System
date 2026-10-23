"""Async coordinator worker: RabbitMQ consumer with a database sweep fallback.

The HTTP route only enqueues a coordination task and returns a task id. This
worker performs the (slow) model work in the background, so closing the page no
longer aborts generation or turns into a 500.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import CoordinationTask
from common.schemas.agent import CoordinationRequest
from services.agent_service.app.services.coordination_runner import run_coordination

LOGGER = logging.getLogger("path-worker")
QUEUE = "path_generation"
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
# The sweep is the only delivery path when RabbitMQ is not running (the local
# Windows dev stack has no broker). The claim is a conditional UPDATE on
# status="QUEUED", so a broker message that arrives later cannot run the task a
# second time; waiting 25 s here used to add ~25 s of dead time to every
# generation before the worker even started.
STALE_QUEUED_SECONDS = 3
SWEEP_INTERVAL_SECONDS = 2


def execute_task(task_id: int) -> None:
    """Claim one queued task and run the coordinator workflow to completion."""

    with SessionLocal() as db:
        claimed = db.query(CoordinationTask).filter_by(id=task_id, status="QUEUED").update(
            {"status": "RUNNING", "started_at": datetime.utcnow(), "worker_id": WORKER_ID},
            synchronize_session=False,
        )
        db.commit()
        if not claimed:
            return
        task = db.get(CoordinationTask, task_id)

        try:
            payload = CoordinationRequest(**task.request_json)
            result = run_coordination(payload, db)
            data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
            task = db.get(CoordinationTask, task_id)
            task.result_json = data
            task.status = "SUCCEEDED"
            task.error_code = ""
            task.error_message = ""
            task.completed_at = datetime.utcnow()
            db.commit()
            LOGGER.info("coordination_task_succeeded task_id=%s", task_id)
        except Exception as exc:  # noqa: BLE001 - the failure is persisted for the UI
            db.rollback()
            LOGGER.exception("coordination_task_failed task_id=%s", task_id)
            task = db.get(CoordinationTask, task_id)
            if task is not None:
                task.status = "FAILED"
                task.error_code = type(exc).__name__
                task.error_message = str(exc)[:500]
                task.completed_at = datetime.utcnow()
                db.commit()


def sweep_stale() -> int:
    """Pick up queued tasks whose broker message was lost or never published."""

    cutoff = datetime.utcnow() - timedelta(seconds=STALE_QUEUED_SECONDS)
    with SessionLocal() as db:
        rows = (
            db.query(CoordinationTask.id)
            .filter(
                CoordinationTask.status == "QUEUED",
                or_(CoordinationTask.created_at.is_(None), CoordinationTask.created_at <= cutoff),
            )
            .order_by(CoordinationTask.id.asc())
            .limit(3)
            .all()
        )
    for (task_id,) in rows:
        execute_task(task_id)
    return len(rows)


def consume_forever() -> None:
    settings = get_settings()
    if not settings.rabbitmq_url:
        LOGGER.warning("rabbitmq_url_missing; running in database-sweep-only mode")
        while True:
            sweep_stale()
            time.sleep(SWEEP_INTERVAL_SECONDS)

    import pika

    parameters = pika.URLParameters(settings.rabbitmq_url)
    parameters.connection_attempts = 1
    parameters.socket_timeout = 5
    parameters.stack_timeout = 10
    while True:
        connection = None
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)

            def on_message(_channel, method, _properties, body) -> None:
                try:
                    payload = json.loads(body.decode("utf-8"))
                    execute_task(int(payload["task_id"]))
                except Exception:
                    LOGGER.exception("coordination_message_failed")
                finally:
                    _channel.basic_ack(method.delivery_tag)

            channel.basic_consume(queue=QUEUE, on_message_callback=on_message, auto_ack=False)
            LOGGER.info("path_worker_started queue=%s worker=%s", QUEUE, WORKER_ID)
            while True:
                connection.process_data_events(time_limit=3)
                sweep_stale()
        except Exception:
            LOGGER.exception("path_worker_connection_lost; retrying in %ss", SWEEP_INTERVAL_SECONDS)
            sweep_stale()
            time.sleep(SWEEP_INTERVAL_SECONDS)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    sweep_stale()
    consume_forever()
