"""Bounded administrator queries over persistent provider metadata."""
import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.model_usage import effective_call_limits
from common.models.learning import AuditLog, KnowledgeBudgetCounter, SystemConfig
from common.models.operations import ModelCall, WorkerInstance

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin"))])


class ModelBudgetPolicy(BaseModel):
    day_call_limit: int | None = Field(None, ge=0, le=1000000)
    user_day_call_limit: int | None = Field(None, ge=0, le=1000000)


@router.get("/model-budget")
def read_budget_policy(db: Session = Depends(get_db), mode: Literal['LIVE', 'TEST'] = 'LIVE'):
    row = db.get(SystemConfig, "model_call_budget")
    counter = db.get(KnowledgeBudgetCounter, f'model-day:{mode}:{datetime.utcnow():%Y%m%d}')
    return {"configured": json.loads(row.value) if row else ModelBudgetPolicy().model_dump(),
            "effective": effective_call_limits(db), "timezone": "UTC",
            "day_call_budget": {'used': counter.model_calls if counter else 0, 'limit': effective_call_limits(db)['day_call_limit']},
            "basis": "Failed attempts count; environment limits cannot be relaxed here"}


@router.put("/model-budget")
def save_budget_policy(payload: ModelBudgetPolicy, db: Session = Depends(get_db)):
    row = db.get(SystemConfig, "model_call_budget")
    if row is None:
        row = SystemConfig(key="model_call_budget", value="{}")
        db.add(row)
    row.value = json.dumps(payload.model_dump())
    db.add(AuditLog(level="INFO", event="MODEL_BUDGET_UPDATED", message="Administrator updated provider call limits"))
    db.commit()
    return read_budget_policy(db)


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


def filtered_calls(db, mode, days, start, end, search='', user_id=None, feature=None, model=None, provider=None, status=None, call_type=None):
    query = db.query(ModelCall).filter(ModelCall.mode == mode)
    if call_type:
        query = query.filter(ModelCall.provider == 'deepseek-tools' if call_type == 'tools' else ModelCall.provider != 'deepseek-tools')
    if start is not None or end is not None:
        from services.agent_service.app.services.dashboard_statistics import calendar_range
        lower, upper = calendar_range(start, end, days)
        query = query.filter(ModelCall.started_at >= lower, ModelCall.started_at < upper)
    else:
        query = query.filter(ModelCall.started_at >= datetime.utcnow()-timedelta(days=days))
    if search:
        query = query.filter(or_(*(column.contains(search, autoescape=True) for column in
            (ModelCall.id, ModelCall.model, ModelCall.feature, ModelCall.request_id))))
    for field, value in ((ModelCall.user_id, user_id), (ModelCall.feature, feature), (ModelCall.model, model), (ModelCall.provider, provider), (ModelCall.status, status)):
        if value is not None:
            query = query.filter(field == value)
    return query


@router.get("/usage")
def list_model_usage(mode: Literal["LIVE", "TEST"] = "LIVE", days: int = Query(7, ge=1, le=90),
    user_id: int | None = Query(None, gt=0), feature: str | None = Query(None, max_length=160),
    model: str | None = Query(None, max_length=160), provider: str | None = Query(None, max_length=40),
    status: Literal["STARTED", "SUCCEEDED", "FAILED"] | None = None,
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    start: date | None = None, end: date | None = None, search: str = Query('', max_length=160),
    call_type: Literal['models', 'tools'] | None = None,
    db: Session = Depends(get_db)):
    query = filtered_calls(db, mode, days, start, end, search, user_id, feature, model, provider, status, call_type)
    groups = {}
    for name, column in (("models", ModelCall.model), ("providers", ModelCall.provider), ("features", ModelCall.feature), ("users", ModelCall.user_id), ("daily", func.date(ModelCall.started_at))):
        groups[name] = [{"key": value, "calls": count, "known_input_subtotal": incoming or 0, "known_output_subtotal": outgoing or 0,
            "unknown_or_partial_calls": incomplete or 0} for value, count, incoming, outgoing, incomplete in query.with_entities(column,
                func.count(ModelCall.id), func.sum(ModelCall.input_tokens), func.sum(ModelCall.output_tokens),
                func.sum(case((ModelCall.usage_status != "KNOWN", 1), else_=0))).group_by(column).limit(100).all()]
    budget = db.get(KnowledgeBudgetCounter, f"model-day:{mode}:{datetime.utcnow():%Y%m%d}")
    limit = effective_call_limits(db)["day_call_limit"]
    return {"mode": mode, "timezone": "UTC", "summary": usage_summary(query), "groups": groups,
        "day_call_budget": {"used": budget.model_calls if budget else 0, "limit": limit,
                            "basis": "Attempt reservations; failed attempts consume the limit; not vendor billing"},
        "items": [serialize_call(row) for row in query.order_by(ModelCall.started_at.desc()).offset((page-1)*size).limit(size).all()],
        "total": query.count(), "page": page, "size": size,
        "coverage": "Instrumented calls since deployment only; no historical backfill; provider billing is not verified"}


@router.get('/usage/export')
def export_model_usage(start: date, end: date, mode: Literal['LIVE', 'TEST'] = 'LIVE',
    search: str = Query('', max_length=160), feature: str | None = Query(None, max_length=160),
    model: str | None = Query(None, max_length=160), provider: str | None = Query(None, max_length=40),
    user_id: int | None = Query(None, gt=0), status: Literal['STARTED', 'SUCCEEDED', 'FAILED'] | None = None,
    call_type: Literal['models', 'tools'] | None = None,
    db: Session = Depends(get_db)):
    query = filtered_calls(db, mode, 7, start, end, search, user_id, feature, model, provider, status, call_type)
    columns = ['id', 'started_at', 'feature', 'model', 'response_model', 'provider', 'user_id', 'status',
               'input_tokens', 'output_tokens', 'cached_input_tokens', 'usage_status', 'error_code']
    # Materialize metadata while the request session is open; refuse unbounded large exports.
    rows = query.order_by(ModelCall.started_at.desc(), ModelCall.id).limit(50001).all()
    if len(rows) > 50000:
        from fastapi import HTTPException
        raise HTTPException(422, 'Export exceeds 50,000 records; narrow the date range')
    def generate():
        yield '\ufeff'
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['time_basis=UTC' if col == 'started_at' else col for col in columns])
        yield buffer.getvalue()
        for row in rows:
            buffer.seek(0)
            buffer.truncate(0)
            values = [str(getattr(row, col)) if getattr(row, col) is not None else '' for col in columns]
            writer.writerow(["'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value for value in values])
            yield buffer.getvalue()
    return StreamingResponse(generate(), media_type='text/csv', headers={'Content-Disposition':'attachment; filename="model-usage.csv"'})


@router.get('/dashboard')
def dashboard_statistics(start: date | None = None, end: date | None = None,
    days: int = Query(7, ge=1, le=90), mode: Literal['LIVE', 'TEST'] = 'LIVE', db: Session = Depends(get_db)):
    from services.agent_service.app.services.dashboard_statistics import calendar_range, statistics
    lower, upper = calendar_range(start, end, days)
    return statistics(db, lower, upper, mode)


@router.get("/workers")
def worker_instances(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    rows = db.query(WorkerInstance).order_by(WorkerInstance.heartbeat_at.desc()).all()
    items = []
    for row in rows:
        age = max(0, (now-row.heartbeat_at).total_seconds())
        status = row.status if row.status != "RUNNING" else "STALE" if age > max(15, row.heartbeat_interval*3) else "DEGRADED" if row.error_code else "ONLINE"
        items.append({"id": row.id, "kind": row.kind, "pid": row.pid, "capabilities": row.capabilities,
            "status": status, "heartbeat_at": row.heartbeat_at, "heartbeat_age_seconds": age,
            "started_at": row.started_at, "stopped_at": row.stopped_at, "batches": row.batches,
            "error_code": row.error_code, "stale_after_seconds": max(15, row.heartbeat_interval*3)})
    return {"items": items, "as_of": now, "status": "REGISTERED" if rows else "NO_REGISTERED_WORKERS",
            "registered": len(items), "active_registered": sum(row['status'] != 'STOPPED' for row in items),
            "distribution": {status: sum(row['status'] == status for row in items) for status in sorted({row['status'] for row in items})},
            "online": sum(row["status"] == "ONLINE" for row in items)}
