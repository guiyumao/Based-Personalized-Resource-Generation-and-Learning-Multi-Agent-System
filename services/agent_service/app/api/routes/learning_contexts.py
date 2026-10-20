"""Persistent learner workspace selections, validated against authoritative rows."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user
from common.learning_context import context_snapshot, create_context
from common.models.learning import LearningPath, User

router = APIRouter(prefix="/learning/contexts", tags=["learning-workspace"])


class ContextCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: str = Field(min_length=8, max_length=80)
    plan_id: int = Field(gt=0)
    module_id: str = Field(min_length=1, max_length=120)
    task_key: str = Field(min_length=1, max_length=120)
    resource_id: int | None = Field(default=None, gt=0)
    expected_resource_version: str | None = Field(default=None, min_length=64, max_length=64)


@router.post("", status_code=201)
def open_context(
    payload: ContextCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    row = create_context(db, user.id, **payload.model_dump())
    return context_snapshot(db, user.id, row.id)


@router.get("/catalog")
def workspace_catalog(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plans = (
        db.query(LearningPath)
        .filter_by(user_id=user.id, status="active")
        .order_by(LearningPath.id.desc())
        .all()
    )
    return {"plans": [{"id": plan.id, "data": plan.path_data_json} for plan in plans]}


@router.get("/{context_id}")
def read_context(
    context_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return context_snapshot(db, user.id, context_id)
