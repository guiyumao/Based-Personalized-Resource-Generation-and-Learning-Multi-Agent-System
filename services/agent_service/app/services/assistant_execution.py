"""Worker ownership guard for assistant side effects."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from common.config import get_settings
from common.models.learning import AssistantTask
from common.db.session import SessionLocal

ExecutionGuard = tuple[int, str, int]
current_execution: ContextVar[ExecutionGuard | None] = ContextVar("assistant_execution", default=None)


class ExecutionStopped(RuntimeError):
    """The task was cancelled or lost its execution lease."""


def lease_conditions(now: datetime | None = None) -> tuple:
    """A paused worker cannot renew or use an already expired lease."""
    now = now or datetime.utcnow()
    settings = get_settings()
    interval = max(1, getattr(settings, "assistant_worker_heartbeat_seconds", 5))
    stale = max(interval * 3, getattr(settings, "assistant_worker_stale_seconds", 45))
    maximum = max(1, getattr(settings, "assistant_task_max_seconds", 1800))
    return (
        func.coalesce(AssistantTask.heartbeat_at, AssistantTask.updated_at) >= now - timedelta(seconds=stale),
        or_(AssistantTask.started_at.is_(None), AssistantTask.started_at >= now - timedelta(seconds=maximum)),
    )


def ensure_execution_active() -> None:
    guard = current_execution.get()
    if guard is None:
        return
    task_id, worker_id, attempt = guard
    with SessionLocal() as db:
        active = db.query(AssistantTask.id).filter(
            AssistantTask.id == task_id, AssistantTask.status == "RUNNING",
            AssistantTask.worker_id == worker_id,
            AssistantTask.execution_attempt == attempt,
            *lease_conditions(),
        ).first()
    if active is None:
        raise ExecutionStopped("assistant task cancellation or lease loss")


def ensure_write_allowed(db: Session) -> None:
    """Fence writes in the same transaction as the side effect.

    The conditional UPDATE also serializes cancellation and persistence on
    SQLite and locks the task row until commit on databases with row locks.
    """
    guard = current_execution.get()
    if guard is None:
        return
    task_id, worker_id, attempt = guard
    updated = db.query(AssistantTask).filter(
        AssistantTask.id == task_id,
        AssistantTask.status == "RUNNING",
        AssistantTask.worker_id == worker_id,
        AssistantTask.execution_attempt == attempt,
        *lease_conditions(),
    ).update({AssistantTask.heartbeat_at: datetime.utcnow()}, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise ExecutionStopped("assistant task cancellation or lease loss")
    task = db.get(AssistantTask, task_id)
    context_id = (task.request_json or {}).get("learning_context_id") if task else None
    if context_id:
        from common.learning_context import validate_context
        try:
            validate_context(db, task.user_id, context_id)
        except Exception as exc:
            db.rollback()
            raise ExecutionStopped("learning context changed or is no longer accessible") from exc
