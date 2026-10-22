"""Coordinator agent routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user, require_self_or_admin
from common.messaging.rabbitmq import RabbitMQPublisher
from common.models.learning import CoordinationTask, User
from common.schemas.agent import CoordinationRequest, CoordinationResponse
from services.agent_service.app.services.coordination_runner import run_coordination

router = APIRouter()

#: Durable queue consumed by the async coordinator worker.
PATH_QUEUE = "path_generation"


def _task_payload(task: CoordinationTask) -> dict:
    return {
        "id": task.id,
        "status": task.status,
        "error_code": task.error_code or "",
        "error_message": task.error_message or "",
        "result": task.result_json or {},
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.post("/coordinate", response_model=CoordinationResponse)
def coordinate(
    payload: CoordinationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoordinationResponse:
    """Execute the coordinator LangGraph workflow synchronously."""
    require_self_or_admin(payload.user_id, current_user)
    return run_coordination(payload, db)


@router.post("/coordinate/async")
def coordinate_async(
    payload: CoordinationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Queue a coordinated request on RabbitMQ and return a task id immediately.

    Long model workflows must not hold the browser request open: navigating away
    used to abort the HTTP call and surface as a 500. The worker keeps running
    and the result stays available through the task endpoint.
    """

    require_self_or_admin(payload.user_id, current_user)
    task = CoordinationTask(
        user_id=payload.user_id,
        status="QUEUED",
        request_json=payload.model_dump(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        RabbitMQPublisher().publish(PATH_QUEUE, {"task_id": task.id})
    except Exception:
        # The broker is optional: the worker also sweeps queued rows from the
        # database, so a failed publish only costs latency, not the request.
        pass

    return {"task_id": task.id, "status": task.status}


@router.get("/coordinate/tasks/{task_id}")
def coordination_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Poll one async coordination task; the owner (or an admin) may read it."""

    task = db.get(CoordinationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    require_self_or_admin(task.user_id, current_user)
    return _task_payload(task)


@router.get("/coordinate/tasks")
def coordination_task_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 10,
) -> dict:
    """Recent async coordination tasks for the current user (bounded)."""

    limit = max(1, min(int(limit), 30))
    rows = (
        db.query(CoordinationTask)
        .filter(CoordinationTask.user_id == current_user.id)
        .order_by(CoordinationTask.id.desc())
        .limit(limit)
        .all()
    )
    return {"items": [_task_payload(row) for row in rows]}
