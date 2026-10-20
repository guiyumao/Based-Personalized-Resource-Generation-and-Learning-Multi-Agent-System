"""Attempt history is written alongside each existing lease transition."""
from datetime import datetime

from sqlalchemy import update

from common.models.operations import TaskAttempt


def started(db, kind, task):
    # The caller's claim transaction holds the task lease fence.
    db.execute(update(TaskAttempt).where(TaskAttempt.task_kind == kind, TaskAttempt.task_id == task.id,
        TaskAttempt.attempt < task.execution_attempt, TaskAttempt.status == "RUNNING").values(
            status="LEASE_LOST", finished_at=datetime.utcnow(), error_code="LEASE_RECLAIMED"))
    row = db.get(TaskAttempt, (kind, task.id, task.execution_attempt))
    if row is None:
        db.add(TaskAttempt(task_kind=kind, task_id=task.id, attempt=task.execution_attempt,
            status="RUNNING", started_at=datetime.utcnow()))
        db.commit()


def finished(db, kind, task_id, attempt, model):
    db.rollback()
    task = db.get(model, task_id, populate_existing=True)
    row = db.get(TaskAttempt, (kind, task_id, attempt))
    if row:
        row.status = task.status if task and task.execution_attempt == attempt else "LEASE_LOST"
        if row.status == "RUNNING":
            row.status = "INTERRUPTED"
        row.error_code = (task.error_code or "")[:80] if task else "TASK_MISSING"
        row.finished_at = datetime.utcnow()
        db.commit()
