"""Administrator task operations from durable records, without prompt disclosure."""

import re
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import (
    AssistantAgentExecution,
    AssistantTask,
    KnowledgeBudgetCounter,
    KnowledgeBuildTask,
)
from common.models.operations import TaskAttempt

router = APIRouter(prefix="/admin/operations", dependencies=[Depends(require_role("admin"))])
MODELS = {"assistant": AssistantTask, "knowledge": KnowledgeBuildTask}


def code(value):
    """Only machine codes, never arbitrary exception text or credentials."""
    return (
        value if re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", value or "") else "REDACTED" if value else ""
    )


def task_summary(kind, task, now):
    interval = max(0, (now - task.heartbeat_at).total_seconds()) if task.heartbeat_at else None
    threshold = max(
        get_settings().assistant_worker_heartbeat_seconds * 3,
        get_settings().assistant_worker_stale_seconds,
    )
    active = task.status in {"RUNNING", "CANCEL_REQUESTED"}
    expired = (
        task.lease_expires_at <= now if kind == "knowledge" and task.lease_expires_at else None
    )
    observation = (
        "HISTORICAL"
        if not active and interval is not None
        else "UNKNOWN"
        if interval is None
        else "STALE"
        if expired or (kind == "assistant" and interval > threshold)
        else "RECENT"
    )
    return {
        "kind": kind,
        "id": task.id,
        "user_id": task.user_id if kind == "assistant" else task.actor_user_id,
        "operation": task.task_type if kind == "assistant" else task.operation_type,
        "status": task.status,
        "attempt": task.execution_attempt,
        "error_code": code(task.error_code),
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "heartbeat_at": task.heartbeat_at,
        "heartbeat_age_seconds": interval,
        "lease_observation": observation,
        "retry_scheduled_at": task.next_attempt_at,
    }


@router.get("")
def operations_overview(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    summaries, recent, daily = {}, [], []
    for kind, model in MODELS.items():
        query = db.query(model).filter(model.created_at >= cutoff)
        summaries[kind] = {
            status: count
            for status, count in db.query(model.status, func.count(model.id))
            .filter(model.created_at >= cutoff)
            .group_by(model.status)
            .all()
        }
        recent.extend(
            task_summary(kind, task, now)
            for task in query.order_by(model.created_at.desc()).limit(30).all()
        )
        daily.extend(
            {"kind": kind, "date": str(day), "count": count}
            for day, count in db.query(func.date(model.created_at), func.count(model.id))
            .filter(model.created_at >= cutoff)
            .group_by(func.date(model.created_at))
            .all()
        )
    budget_scopes = [f"day:{now:%Y%m%d}", f"month:{now:%Y%m}"]
    from services.agent_service.app.api.routes.model_usage import usage_summary, worker_instances
    from common.models.operations import ModelCall
    usage = usage_summary(db.query(ModelCall).filter(ModelCall.mode == "LIVE", ModelCall.started_at >= cutoff))
    worker_data = worker_instances(db)
    budgets = [
        {
            "scope": row.scope_key,
            "search_calls": row.search_calls,
            "fetch_calls": row.fetch_calls,
            "model_calls": row.model_calls,
            "reserved_input_tokens": row.input_tokens,
            "reserved_output_tokens": row.output_tokens,
            "reserved_cost_micros": row.reserved_cost_micros,
        }
        for row in db.query(KnowledgeBudgetCounter)
        .filter(KnowledgeBudgetCounter.scope_key.in_(budget_scopes))
        .all()
    ]
    return {
        "days": days,
        "timezone": "UTC",
        "as_of": now,
        "counts": summaries,
        "recent_tasks": sorted(recent, key=lambda row: row["created_at"], reverse=True)[:50],
        "daily_tasks": daily,
        "knowledge_budget_reservations": budgets,
        "actual_model_usage": usage if usage["calls"] else {
            "status": "UNKNOWN",
            "input_tokens": None,
            "output_tokens": None,
            "calls": None,
            "reason": "No complete durable per-call provider ledger; reservations and performance estimates are not actual usage",
        },
        "worker_health": worker_data["status"],
        "workers": worker_data["items"],
        "worker_basis": "Independent Worker registry; uninstrumented old processes are not observable",
    }


@router.get("/tasks/{kind}/{task_id}")
def operation_task(
    kind: Literal["assistant", "knowledge"], task_id: int, db: Session = Depends(get_db)
):
    task = db.get(MODELS[kind], task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    result = task_summary(kind, task, datetime.utcnow())
    result["stages"] = (
        [
            {
                "agent": row.agent_code,
                "status": row.status,
                "elapsed_ms": row.elapsed_ms,
                "error_code": code(row.error_code),
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
            for row in db.query(AssistantAgentExecution)
            .filter_by(task_id=task.id)
            .order_by(AssistantAgentExecution.id)
            .all()
        ]
        if kind == "assistant"
        else []
    )
    result["history_basis"] = (
        "Persisted stages and attempts since instrumentation; historical attempts are not backfilled"
    )
    result["attempts"] = [{"attempt": row.attempt, "status": row.status, "started_at": row.started_at,
        "finished_at": row.finished_at, "error_code": code(row.error_code)} for row in db.query(TaskAttempt).filter_by(
            task_kind=kind, task_id=task_id).order_by(TaskAttempt.attempt).all()]
    return result
