"""Bounded administrator queries over persistent provider metadata."""
import os
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import KnowledgeBudgetCounter
from common.models.operations import ModelCall, WorkerInstance

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin"))])


def serialize_call(row):
    return {column.name: getattr(row, column.name) for column in ModelCall.__table__.columns}


def usage_summary(query):
    calls, known, incoming, outgoing, missing_in, missing_out = query.with_entities(
        func.count(ModelCall.id), func.sum(case((ModelCall.usage_status == "KNOWN", 1), else_=0)),
        func.sum(ModelCall.input_tokens), func.sum(ModelCall.output_tokens),
        func.sum(case((ModelCall.input_tokens.is_(None), 1), else_=0)),
        func.sum(case((ModelCall.output_tokens.is_(None), 1), else_=0))).one()
    return {"calls": calls, "known_usage_calls": known or 0, "unknown_or_partial_calls": calls - (known or 0),
            "input_tokens": None if missing_in else incoming or 0, "output_tokens": None if missing_out else outgoing or 0,
            "known_input_subtotal": incoming or 0, "known_output_subtotal": outgoing or 0,
            "usage_status": "EMPTY" if not calls else "KNOWN" if known == calls else "INCOMPLETE",
            "cost": None, "cost_status": "NO_VERIFIED_PRICING", "cached_tokens_included_in_input": True}


@router.get("/usage")
def list_model_usage(mode: Literal["LIVE", "TEST"] = "LIVE", days: int = Query(7, ge=1, le=90),
    user_id: int | None = Query(None, gt=0), feature: str | None = Query(None, max_length=160),
    model: str | None = Query(None, max_length=160), provider: str | None = Query(None, max_length=40),
    status: Literal["STARTED", "SUCCEEDED", "FAILED"] | None = None,
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = db.query(ModelCall).filter(ModelCall.mode == mode, ModelCall.started_at >= datetime.utcnow()-timedelta(days=days))
    for field, value in ((ModelCall.user_id, user_id), (ModelCall.feature, feature), (ModelCall.model, model), (ModelCall.provider, provider), (ModelCall.status, status)):
        if value is not None:
            query = query.filter(field == value)
    groups = {}
    for name, column in (("models", ModelCall.model), ("providers", ModelCall.provider), ("features", ModelCall.feature), ("users", ModelCall.user_id), ("daily", func.date(ModelCall.started_at))):
        groups[name] = [{"key": value, "calls": count, "known_input_subtotal": incoming or 0, "known_output_subtotal": outgoing or 0,
            "unknown_or_partial_calls": incomplete or 0} for value, count, incoming, outgoing, incomplete in query.with_entities(column,
                func.count(ModelCall.id), func.sum(ModelCall.input_tokens), func.sum(ModelCall.output_tokens),
                func.sum(case((ModelCall.usage_status != "KNOWN", 1), else_=0))).group_by(column).limit(100).all()]
    budget = db.get(KnowledgeBudgetCounter, f"model-day:{mode}:{datetime.utcnow():%Y%m%d}")
    limit = os.getenv("AI_PROVIDER_DAY_CALL_LIMIT")
    return {"mode": mode, "timezone": "UTC", "summary": usage_summary(query), "groups": groups,
        "day_call_budget": {"used": budget.model_calls if budget else 0, "limit": int(limit) if limit is not None else None,
                            "basis": "Attempt reservations; failed attempts consume the limit; not vendor billing"},
        "items": [serialize_call(row) for row in query.order_by(ModelCall.started_at.desc()).offset((page-1)*size).limit(size).all()],
        "total": query.count(), "page": page, "size": size,
        "coverage": "Instrumented calls since deployment only; no historical backfill; provider billing is not verified"}


@router.get("/workers")
def worker_instances(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    rows = db.query(WorkerInstance).order_by(WorkerInstance.started_at.desc()).limit(100).all()
    items = []
    for row in rows:
        age = max(0, (now-row.heartbeat_at).total_seconds())
        status = row.status if row.status != "RUNNING" else "STALE" if age > max(15, row.heartbeat_interval*3) else "DEGRADED" if row.error_code else "ONLINE"
        items.append({"id": row.id, "kind": row.kind, "pid": row.pid, "capabilities": row.capabilities,
            "status": status, "heartbeat_at": row.heartbeat_at, "heartbeat_age_seconds": age,
            "started_at": row.started_at, "stopped_at": row.stopped_at, "batches": row.batches,
            "error_code": row.error_code, "stale_after_seconds": max(15, row.heartbeat_interval*3)})
    return {"items": items, "as_of": now, "status": "REGISTERED" if rows else "NO_REGISTERED_WORKERS",
            "online": sum(row["status"] == "ONLINE" for row in items)}
