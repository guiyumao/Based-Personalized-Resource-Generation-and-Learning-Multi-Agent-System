"""Teacher-owned resources, evidence and personalized homework review/publish."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from common.dependencies import require_role
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.course_support import (
    DeliveryCreate,
    DeliveryItem,
    DraftEdit,
    DraftPublish,
    ReinforcementCreate,
)
from services.teacher_service.app.services import course_support as service

router = APIRouter()


def _call(function, *args):
    try:
        return function(*args)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/classes/{class_id}/resource-catalog", response_model=ApiResponse[list[dict]])
def catalog(class_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(service.catalog, class_id, user.id))


@router.get("/classes/{class_id}/course-resources", response_model=ApiResponse[list[DeliveryItem]])
def deliveries(class_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(service.deliveries, class_id, user.id))


@router.post("/classes/{class_id}/course-resources", response_model=ApiResponse[DeliveryItem])
def deliver(class_id: int, payload: DeliveryCreate, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(service.deliver, class_id, user.id, payload))


@router.get("/students/me/course-resources", response_model=ApiResponse[list[DeliveryItem]])
def student_resources(user: User = Depends(require_role("student"))):
    return ApiResponse(data=service.student_deliveries(user.id))


@router.get("/classes/{class_id}/students/{student_id}/reinforcement-evidence", response_model=ApiResponse[dict])
def evidence(class_id: int, student_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(service.evidence, class_id, user.id, student_id))


@router.get("/classes/{class_id}/reinforcements", response_model=ApiResponse[list[dict]])
def drafts(class_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(service.list_drafts, class_id, user.id))


@router.post("/classes/{class_id}/reinforcements", response_model=ApiResponse[dict])
def generate(class_id: int, payload: ReinforcementCreate, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(service.generate, class_id, user.id, payload))


@router.put("/reinforcements/{draft_id}", response_model=ApiResponse[dict])
def edit(draft_id: int, payload: DraftEdit, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(service.edit, draft_id, user.id, payload))


@router.post("/reinforcements/{draft_id}/publish", response_model=ApiResponse[dict])
def publish(draft_id: int, payload: DraftPublish, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(service.publish, draft_id, user.id, payload))


@router.get("/classes/{class_id}/reinforcement-attempts", response_model=ApiResponse[list[dict]])
def attempts(class_id: int, user: User = Depends(require_role("teacher"))):
    from services.teacher_service.app.services.reinforcement_feedback import teacher_attempts
    return ApiResponse(data=_call(teacher_attempts, class_id, user.id))


@router.post("/reinforcement-attempts/{attempt_id}/analyze", response_model=ApiResponse[dict])
def retry_analysis(attempt_id: int, background_tasks: BackgroundTasks, user: User = Depends(require_role("teacher"))):
    from services.teacher_service.app.services.reinforcement_feedback import (
        analyze_attempt,
        authorize_retry,
    )
    result = _call(authorize_retry, attempt_id, user.id)
    background_tasks.add_task(analyze_attempt, attempt_id)
    return ApiResponse(data=result)
