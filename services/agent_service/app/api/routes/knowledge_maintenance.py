"""Administrator maintenance plans for the shared knowledge task queue."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import KnowledgeMaintenancePlan, User
from services.agent_service.app.services.knowledge_maintenance import MaintenancePolicy, create_plan, plan_to_dict

router = APIRouter(prefix="/knowledge-base/maintenance-plans", tags=["knowledge-maintenance"])


class MaintenancePlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="", max_length=100)
    next_run_at: datetime
    interval_hours: int | None = Field(default=None, ge=24, le=24 * 365)
    policy: MaintenancePolicy | None = None


class MaintenancePlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    subject: str | None = Field(default=None, max_length=100)
    next_run_at: datetime | None = None
    interval_hours: int | None = Field(default=None, ge=24, le=24 * 365)
    enabled: bool | None = None
    policy: MaintenancePolicy | None = None


@router.post("", status_code=201)
def create_maintenance_plan(
    payload: MaintenancePlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    try:
        plan = create_plan(
            db, actor_user_id=current_user.id, name=payload.name, subject=payload.subject,
            next_run_at=payload.next_run_at, interval_hours=payload.interval_hours,
            policy=payload.policy.model_dump() if payload.policy else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return plan_to_dict(plan)


@router.get("")
def list_maintenance_plans(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> dict:
    plans = db.query(KnowledgeMaintenancePlan).order_by(KnowledgeMaintenancePlan.id.desc()).limit(100).all()
    return {"items": [plan_to_dict(plan) for plan in plans]}


@router.patch("/{plan_id}")
def update_maintenance_plan(
    plan_id: int,
    payload: MaintenancePlanUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> dict:
    plan = db.get(KnowledgeMaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Maintenance plan not found")
    fields = payload.model_fields_set
    if "policy" in fields and payload.policy is not None:
        plan.policy_json = payload.policy.model_dump()
    if "name" in fields and payload.name is not None:
        plan.name = payload.name.strip()
    if "subject" in fields and payload.subject is not None:
        plan.subject = payload.subject.strip()
    if "interval_hours" in fields:
        plan.interval_hours = payload.interval_hours
    if "next_run_at" in fields:
        if payload.next_run_at is None or payload.next_run_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="An explicit next run time and timezone are required")
        plan.next_run_at = payload.next_run_at.astimezone(timezone.utc).replace(tzinfo=None)
        if plan.next_run_at <= datetime.utcnow():
            raise HTTPException(status_code=422, detail="Next run must be in the future")
    if "enabled" in fields and payload.enabled is not None:
        if payload.enabled and plan.next_run_at is None:
            raise HTTPException(status_code=409, detail="A completed one-time plan needs a new run time")
        plan.enabled = payload.enabled
    db.commit()
    db.refresh(plan)
    return plan_to_dict(plan)


@router.get("/{plan_id}/reports")
def maintenance_reports(plan_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    from common.models.learning import KnowledgeBuildTask
    from services.agent_service.app.services.knowledge_tasks import serialize_task
    plan = db.get(KnowledgeMaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Maintenance plan not found")
    items = db.query(KnowledgeBuildTask).filter(KnowledgeBuildTask.client_request_id.like(f"maintenance-{plan_id}-%"),
                                                KnowledgeBuildTask.trigger_source.in_(("ADMIN_SCHEDULED", "ADMIN_ONE_TIME_SCHEDULED"))).order_by(KnowledgeBuildTask.id.desc()).limit(30).all()
    return {"items": [serialize_task(item) for item in items], "next_run_at": plan_to_dict(plan)["next_run_at"]}
