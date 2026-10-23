"""Learning check-in and classroom attendance routes.

Auth classification:
- GET  /home, /tasks, /self, /calendar, /attendance        : PROTECTED (student)
- POST /self, /tasks/{id}/submit, /attendance/checkin      : PROTECTED (student)
- GET  /overview, /tasks, /attendance/sessions             : PROTECTED (teacher, admin)
- POST /tasks, /attendance, publish/close/review/remind    : PROTECTED (teacher)
- GET  /admin/overview, /admin/audits                      : PROTECTED (admin)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from common.dependencies import require_role
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.checkin import (
    AdminCheckinOverview,
    AttendanceCheckinPayload,
    AttendanceLive,
    AttendanceSessionCreate,
    AttendanceSessionItem,
    AttendanceUpdatePayload,
    CheckinHome,
    CheckinRemindPayload,
    CheckinReviewBatch,
    CheckinReviewPayload,
    CheckinSubmissionItem,
    CheckinSubmitPayload,
    CheckinTaskCompletion,
    CheckinTaskCreate,
    CheckinTaskDetail,
    CheckinTaskItem,
    CheckinTaskUpdate,
    DailyCheckinItem,
    DailyCheckinPayload,
    PlatformCheckinCalendar,
    PlatformCheckinStatus,
    TeacherCheckinOverview,
)
from services.teacher_service.app.services.checkin_manager import CheckinManager

router = APIRouter()
manager = CheckinManager()


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ------------------------------------------------------------------ student
@router.get("/home", response_model=ApiResponse[CheckinHome])
def student_home(user: User = Depends(require_role("student"))):
    return ApiResponse(data=manager.home(user.id))


@router.get("/tasks", response_model=ApiResponse[list[CheckinTaskItem]])
def student_tasks(
    include_closed: bool = Query(default=False),
    user: User = Depends(require_role("student")),
):
    return ApiResponse(data=manager.list_student_tasks(user.id, include_closed))


@router.get("/tasks/{task_id}", response_model=ApiResponse[CheckinTaskDetail])
def student_task_detail(task_id: int, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_call(manager.student_task_detail, task_id, user.id))


@router.post("/tasks/{task_id}/submit", response_model=ApiResponse[CheckinSubmissionItem])
def student_submit_task(
    task_id: int,
    payload: CheckinSubmitPayload,
    user: User = Depends(require_role("student")),
):
    return ApiResponse(data=_call(manager.submit_task, task_id, user.id, payload))


@router.get("/submissions/me", response_model=ApiResponse[list[CheckinSubmissionItem]])
def student_submissions(user: User = Depends(require_role("student"))):
    return ApiResponse(data=manager.list_my_submissions(user.id))


@router.get("/daily", response_model=ApiResponse[PlatformCheckinStatus])
def daily_status(user: User = Depends(require_role("student"))):
    """Platform check-in status; independent from classrooms and attendance."""

    return ApiResponse(data=manager.daily_status(user.id))


@router.post("/daily", response_model=ApiResponse[PlatformCheckinStatus])
def daily_checkin(payload: DailyCheckinPayload, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_call(manager.daily_checkin, user.id, payload))


@router.get("/daily/history", response_model=ApiResponse[list[DailyCheckinItem]])
def daily_history(user: User = Depends(require_role("student"))):
    return ApiResponse(data=manager.daily_history(user.id))


@router.get("/daily/calendar", response_model=ApiResponse[PlatformCheckinCalendar])
def daily_calendar(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    user: User = Depends(require_role("student")),
):
    return ApiResponse(data=_call(manager.daily_calendar, user.id, month))


@router.get("/attendance", response_model=ApiResponse[list[AttendanceSessionItem]])
def student_attendance(user: User = Depends(require_role("student"))):
    return ApiResponse(data=manager.list_student_attendance(user.id))


@router.post("/attendance/checkin", response_model=ApiResponse[AttendanceSessionItem])
def checkin_attendance(
    payload: AttendanceCheckinPayload,
    user: User = Depends(require_role("student")),
):
    return ApiResponse(
        data=_call(manager.checkin_attendance, user.id, payload.code, payload.token)
    )


# ------------------------------------------------------------------ teacher
@router.get("/overview", response_model=ApiResponse[TeacherCheckinOverview])
def teacher_overview(user: User = Depends(require_role("teacher", "admin"))):
    return ApiResponse(data=manager.teacher_overview(user.id, user.role))


@router.get("/manage/tasks", response_model=ApiResponse[list[CheckinTaskItem]])
def teacher_tasks(
    class_id: int | None = Query(default=None, gt=0),
    user: User = Depends(require_role("teacher", "admin")),
):
    return ApiResponse(data=manager.list_teacher_tasks(user.id, user.role, class_id))


@router.post("/manage/tasks", response_model=ApiResponse[CheckinTaskItem])
def create_task(payload: CheckinTaskCreate, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(manager.create_task, user.id, payload))


@router.put("/manage/tasks/{task_id}", response_model=ApiResponse[CheckinTaskItem])
def update_task(
    task_id: int, payload: CheckinTaskUpdate, user: User = Depends(require_role("teacher"))
):
    return ApiResponse(data=_call(manager.update_task, task_id, user.id, user.role, payload))


@router.post("/manage/tasks/{task_id}/publish", response_model=ApiResponse[CheckinTaskItem])
def publish_task(task_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(manager.publish_task, task_id, user.id, user.role))


@router.post("/manage/tasks/{task_id}/close", response_model=ApiResponse[CheckinTaskItem])
def close_task(task_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(manager.close_task, task_id, user.id, user.role))


@router.post("/manage/tasks/{task_id}/cancel", response_model=ApiResponse[CheckinTaskItem])
def cancel_task(task_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(manager.cancel_task, task_id, user.id, user.role))


@router.get(
    "/manage/tasks/{task_id}/completion", response_model=ApiResponse[CheckinTaskCompletion]
)
def task_completion(
    task_id: int,
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: User = Depends(require_role("teacher", "admin")),
):
    return ApiResponse(
        data=_call(manager.task_completion, task_id, user.id, user.role, period)
    )


@router.get(
    "/manage/tasks/{task_id}/submissions",
    response_model=ApiResponse[list[CheckinSubmissionItem]],
)
def task_submissions(
    task_id: int,
    status: str | None = Query(default=None, pattern="^(submitted|approved|returned)$"),
    user: User = Depends(require_role("teacher", "admin")),
):
    return ApiResponse(
        data=_call(manager.list_task_submissions, task_id, user.id, user.role, status)
    )


@router.post(
    "/manage/submissions/{submission_id}/review",
    response_model=ApiResponse[CheckinSubmissionItem],
)
def review_submission(
    submission_id: int,
    payload: CheckinReviewPayload,
    user: User = Depends(require_role("teacher")),
):
    return ApiResponse(
        data=_call(manager.review_submission, submission_id, user.id, user.role, payload)
    )


@router.post("/manage/submissions/review-batch", response_model=ApiResponse[dict])
def batch_review(
    payload: CheckinReviewBatch,
    user: User = Depends(require_role("teacher")),
):
    return ApiResponse(
        data=_call(manager.batch_review, payload.submission_ids, user.id, user.role, payload)
    )


@router.post("/manage/tasks/{task_id}/remind", response_model=ApiResponse[dict])
def remind_task(
    task_id: int,
    payload: CheckinRemindPayload,
    user: User = Depends(require_role("teacher")),
):
    return ApiResponse(
        data=_call(manager.remind_task, task_id, user.id, user.role, payload.period_key)
    )


# --------------------------------------------------------------- attendance
@router.post("/manage/attendance", response_model=ApiResponse[AttendanceSessionItem])
def create_attendance(
    payload: AttendanceSessionCreate, user: User = Depends(require_role("teacher"))
):
    return ApiResponse(data=_call(manager.create_attendance, user.id, payload))


@router.get("/manage/attendance", response_model=ApiResponse[list[AttendanceSessionItem]])
def list_attendance(
    class_id: int | None = Query(default=None, gt=0),
    user: User = Depends(require_role("teacher", "admin")),
):
    return ApiResponse(data=manager.list_teacher_attendance(user.id, user.role, class_id))


@router.get("/manage/attendance/{session_id}/live", response_model=ApiResponse[AttendanceLive])
def attendance_live(
    session_id: int, user: User = Depends(require_role("teacher", "admin"))
):
    return ApiResponse(data=_call(manager.attendance_live, session_id, user.id, user.role))


@router.post(
    "/manage/attendance/{session_id}/close", response_model=ApiResponse[AttendanceSessionItem]
)
def close_attendance(session_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_call(manager.close_attendance, session_id, user.id, user.role))


@router.post(
    "/manage/attendance/{session_id}/students/{student_id}",
    response_model=ApiResponse[AttendanceSessionItem],
)
def update_attendance_record(
    session_id: int,
    student_id: int,
    payload: AttendanceUpdatePayload,
    user: User = Depends(require_role("teacher")),
):
    return ApiResponse(
        data=_call(
            manager.update_attendance_record, session_id, student_id, user.id, payload
        )
    )


# -------------------------------------------------------------------- admin
@router.get("/admin/overview", response_model=ApiResponse[AdminCheckinOverview])
def admin_overview(_user: User = Depends(require_role("admin"))):
    return ApiResponse(data=manager.admin_overview())


@router.get("/admin/audits", response_model=ApiResponse[list[dict]])
def admin_audits(
    limit: int = Query(default=200, ge=1, le=500),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: int | None = Query(default=None, gt=0),
    actor_user_id: int | None = Query(default=None, gt=0),
    keyword: str | None = Query(default=None, max_length=100),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    _user: User = Depends(require_role("admin")),
):
    return ApiResponse(
        data=manager.list_audits(
            limit=limit,
            action=action or None,
            target_type=target_type or None,
            target_id=target_id,
            actor_user_id=actor_user_id,
            keyword=keyword or None,
            start=start,
            end=end,
        )
    )
