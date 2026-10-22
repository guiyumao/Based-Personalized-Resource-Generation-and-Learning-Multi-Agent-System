"""Teacher classroom schedule and student timetable routes.

Auth classification:
- GET  /classes/{id}/schedule                     : teacher (owner), admin
- POST/PUT/DELETE /classes/{id}/schedule*         : teacher (owner)
- GET  /schedule/me                              : student
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from common.dependencies import require_role
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.schedule import (
    ClassSessionItem,
    ClassSessionPayload,
    PersonalScheduleItem,
    PersonalSchedulePayload,
    ScheduleExceptionItem,
    ScheduleExceptionPayload,
    StudentSchedule,
    TeacherSchedule,
)
from services.teacher_service.app.services.classroom_schedule import ClassScheduleManager
from services.teacher_service.app.services.personal_schedule import delete_personal, save_personal

router = APIRouter()
manager = ClassScheduleManager()


def _call(function, *args):
    try:
        return function(*args)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/classes/{class_id}/schedule", response_model=ApiResponse[TeacherSchedule])
def teacher_schedule(
    class_id: int, user: User = Depends(require_role("teacher", "admin"))
):
    return ApiResponse(data=_call(manager.teacher_schedule, class_id, user.id, user.role))


@router.post("/classes/{class_id}/schedule", response_model=ApiResponse[ClassSessionItem])
def create_session(
    class_id: int, payload: ClassSessionPayload, user: User = Depends(require_role("teacher"))
):
    return ApiResponse(data=_call(manager.create_session, class_id, user.id, payload))


@router.put(
    "/classes/{class_id}/schedule/{session_id}", response_model=ApiResponse[ClassSessionItem]
)
def update_session(
    class_id: int,
    session_id: int,
    payload: ClassSessionPayload,
    user: User = Depends(require_role("teacher")),
):
    return ApiResponse(data=_call(manager.update_session, session_id, user.id, payload))


@router.delete(
    "/classes/{class_id}/schedule/{session_id}", response_model=ApiResponse[dict]
)
def delete_session(
    class_id: int, session_id: int, user: User = Depends(require_role("teacher"))
):
    return ApiResponse(data=_call(manager.delete_session, session_id, user.id))


@router.post(
    "/classes/{class_id}/schedule/{session_id}/exceptions",
    response_model=ApiResponse[ScheduleExceptionItem],
)
def add_exception(
    class_id: int,
    session_id: int,
    payload: ScheduleExceptionPayload,
    user: User = Depends(require_role("teacher")),
):
    return ApiResponse(data=_call(manager.add_exception, session_id, user.id, payload))


@router.delete(
    "/classes/{class_id}/schedule/exceptions/{exception_id}", response_model=ApiResponse[dict]
)
def delete_exception(
    class_id: int, exception_id: int, user: User = Depends(require_role("teacher"))
):
    return ApiResponse(data=_call(manager.delete_exception, exception_id, user.id))


@router.get("/schedule/me", response_model=ApiResponse[StudentSchedule])
def my_schedule(
    week_start: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: User = Depends(require_role("student")),
):
    return ApiResponse(data=_call(manager.student_schedule, user.id, week_start))


@router.post("/schedule/me/personal", response_model=ApiResponse[PersonalScheduleItem])
def create_personal(payload: PersonalSchedulePayload, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_call(save_personal, manager, user.id, payload))


@router.put("/schedule/me/personal/{entry_id}", response_model=ApiResponse[PersonalScheduleItem])
def update_personal(entry_id: int, payload: PersonalSchedulePayload, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_call(save_personal, manager, user.id, payload, entry_id))


@router.delete("/schedule/me/personal/{entry_id}", response_model=ApiResponse[dict])
def remove_personal(entry_id: int, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_call(delete_personal, manager, user.id, entry_id))
