"""Administrator endpoints for durable knowledge tasks."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import KnowledgeBuildTask, User
from services.agent_service.app.services.knowledge_tasks import (
    KnowledgeTaskConflict,
    cancel_task,
    create_task,
    serialize_task,
    request_cancel,
    retry_task,
)

router = APIRouter(prefix="/knowledge-base/tasks", tags=["knowledge-tasks"])


class KnowledgeTaskRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=80)
    operation_type: Literal["KNOWLEDGE_HEALTH_CHECK", "INDEX_REPAIR", "SEARCH_SOURCES", "FETCH_SOURCE"]
    subject: str = Field(default="", max_length=100)
    query: str = Field(default="", max_length=128)
    source_task_id: int | None = None
    source_index: int | None = None


@router.post("", status_code=202)
def create_knowledge_task(
    payload: KnowledgeTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    try:
        task = create_task(
            db, actor_user_id=current_user.id, client_request_id=payload.client_request_id,
            operation_type=payload.operation_type, subject=payload.subject,
            requirements=(
                {"query": payload.query} if payload.operation_type == "SEARCH_SOURCES"
                else {"source_task_id": payload.source_task_id, "source_index": payload.source_index}
                if payload.operation_type == "FETCH_SOURCE" else {}
            ),
        )
    except KnowledgeTaskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_task(task)


@router.get("")
def list_knowledge_tasks(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> dict:
    tasks = db.query(KnowledgeBuildTask).order_by(KnowledgeBuildTask.id.desc()).limit(limit).all()
    return {"items": [serialize_task(task) for task in tasks]}


@router.get("/{task_id}")
def get_knowledge_task(
    task_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> dict:
    task = db.get(KnowledgeBuildTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Knowledge task not found")
    return serialize_task(task)


@router.get("/{task_id}/usage")
def knowledge_task_usage(task_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    from services.agent_service.app.services.knowledge_budget import task_usage
    if db.get(KnowledgeBuildTask, task_id) is None:
        raise HTTPException(404, "Knowledge task not found")
    return {"task_id": task_id, "reservations": task_usage(task_id), "actual_model_usage": (db.get(KnowledgeBuildTask, task_id).result_json or {}).get("usage"), "billing_verified": False}


@router.post("/{task_id}/cancel")
def cancel_knowledge_task(
    task_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> dict:
    task = db.get(KnowledgeBuildTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Knowledge task not found")
    try:
        return serialize_task(cancel_task(db, task))
    except KnowledgeTaskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{task_id}/request-cancel")
def request_knowledge_cancel(task_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    task = db.get(KnowledgeBuildTask, task_id)
    if task is None:
        raise HTTPException(404, "Knowledge task not found")
    try:
        return serialize_task(request_cancel(db, task))
    except KnowledgeTaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{task_id}/retry")
def retry_knowledge_task(task_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    task = db.get(KnowledgeBuildTask, task_id)
    if task is None:
        raise HTTPException(404, "Knowledge task not found")
    try:
        return serialize_task(retry_task(db, task))
    except KnowledgeTaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc
