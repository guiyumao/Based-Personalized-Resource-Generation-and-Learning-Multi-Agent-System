"""Teacher class management routes.

Auth classification:
- GET  /classes                           : PROTECTED (teacher, admin)
- POST /classes                           : PROTECTED (teacher only)
- GET  /classes/{id}/progress             : PROTECTED (teacher, admin)
- GET  /classes/{id}/insights             : PROTECTED (teacher, admin)
- GET  /classes/{id}/students/{uid}       : PROTECTED (teacher, admin)
- GET  /classes/{id}/teaching-scopes      : PROTECTED (teacher, admin)
- POST /teaching-scopes                   : PROTECTED (teacher only)
- GET  /classes/{id}/teaching-analytics   : PROTECTED (teacher, admin)
- POST /homework/assign                   : PROTECTED (teacher only)
- POST /homework/{id}/review              : PROTECTED (teacher only)
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from common.dependencies import get_current_user, require_role
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.teacher import (
    AssignmentItem,
    ClassCreate,
    ClassItem,
    ClassJoin,
    ClassMember,
    ClassUpdate,
    EnrollmentCreate,
    HomeworkAssign,
    ReviewPayload,
    StudentInsight,
    StudentLearningDetail,
    SubmissionCreate,
    SubmissionItem,
    TeacherTeachingAnalytics,
    TeachingScopeCreate,
    TeachingScopeItem,
)
from services.teacher_service.app.services.teacher_manager import TeacherManager

router = APIRouter()
manager = TeacherManager()


def _enforce_class_access(class_id: int, user: User) -> None:
    try:
        manager.ensure_teacher_class_access(class_id, user.id, user.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/classes", response_model=ApiResponse[list[ClassItem]])
def list_classes(
    current_user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[ClassItem]]:
    """List all classes. (teacher, admin)"""

    return ApiResponse(
        data=manager.list_classes(current_user.id, current_user.role),
        message="Classes fetched successfully.",
    )


@router.post("/classes", response_model=ApiResponse[ClassItem])
def create_class(
    payload: ClassCreate,
    _user: User = Depends(require_role("teacher")),
) -> ApiResponse[ClassItem]:
    """Create a new class. (teacher only)"""

    return ApiResponse(
        data=manager.create_class(payload, _user.id), message="Class created successfully."
    )


@router.post("/classes/{class_id}/enrollments", response_model=ApiResponse[ClassItem])
def enroll_student(
    class_id: int,
    payload: EnrollmentCreate,
    current_user: User = Depends(require_role("teacher")),
) -> ApiResponse[ClassItem]:
    try:
        item = manager.enroll_student(class_id, payload.student_user_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=item, message="Student enrolled successfully.")


@router.get("/classes/{class_id}/progress", response_model=ApiResponse[dict[str, object]])
def get_class_progress(
    class_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[dict[str, object]]:
    """Get class progress overview. (teacher, admin)"""

    _enforce_class_access(class_id, current_user)
    return ApiResponse(
        data=manager.get_student_progress(class_id),
        message="Class progress fetched successfully.",
    )


@router.get("/classes/{class_id}/insights", response_model=ApiResponse[list[StudentInsight]])
def get_class_insights(
    class_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[StudentInsight]]:
    """Get student insights for one class. (teacher, admin)"""

    _enforce_class_access(class_id, current_user)
    return ApiResponse(
        data=manager.list_student_insights(class_id),
        message="Class student insights fetched successfully.",
    )


@router.get(
    "/classes/{class_id}/students/{user_id}", response_model=ApiResponse[StudentLearningDetail]
)
async def get_student_learning_detail(
    class_id: int,
    user_id: int,
    request: Request,
    current_user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[StudentLearningDetail]:
    """Get one student's detailed mistake notebook and learning reports. (teacher, admin)"""

    _enforce_class_access(class_id, current_user)
    try:
        detail = await manager.get_student_learning_detail(
            class_id, user_id, auth_header=request.headers.get("authorization")
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ApiResponse(
        data=detail,
        message="Student learning detail fetched successfully.",
    )


@router.get(
    "/classes/{class_id}/teaching-scopes", response_model=ApiResponse[list[TeachingScopeItem]]
)
def list_teaching_scopes(
    class_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[TeachingScopeItem]]:
    """List teacher-defined scopes for one class. (teacher, admin)"""

    _enforce_class_access(class_id, current_user)
    return ApiResponse(
        data=manager.list_teaching_scopes(class_id),
        message="Teaching scopes fetched successfully.",
    )


@router.post("/teaching-scopes", response_model=ApiResponse[TeachingScopeItem])
def create_teaching_scope(
    payload: TeachingScopeCreate,
    current_user: User = Depends(require_role("teacher")),
) -> ApiResponse[TeachingScopeItem]:
    """Define learning scope, direction, and courseware for students. (teacher only)"""

    _enforce_class_access(payload.class_id, current_user)
    return ApiResponse(
        data=_membership_call(manager.create_teaching_scope, payload),
        message="Teaching scope created successfully.",
    )


@router.get("/students/me/teaching-scopes", response_model=ApiResponse[list[TeachingScopeItem]])
def list_my_teaching_scopes(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[TeachingScopeItem]]:
    """List teacher-defined scopes delivered to the current student."""

    return ApiResponse(
        data=manager.list_student_teaching_scopes(current_user.id),
        message="Student teaching scopes fetched successfully.",
    )


@router.get(
    "/students/{user_id}/teaching-scopes", response_model=ApiResponse[list[TeachingScopeItem]]
)
def list_student_teaching_scopes(
    user_id: int,
    _user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[TeachingScopeItem]]:
    """List teacher-defined scopes visible to one learner. (teacher, admin)"""

    allowed = {item.id for item in manager.list_classes(_user.id, _user.role)}
    return ApiResponse(
        data=[
            item
            for item in manager.list_student_teaching_scopes(user_id)
            if item.class_id in allowed
        ],
        message="Student teaching scopes fetched successfully.",
    )


@router.get(
    "/classes/{class_id}/teaching-analytics", response_model=ApiResponse[TeacherTeachingAnalytics]
)
def get_teaching_analytics(
    class_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[TeacherTeachingAnalytics]:
    """Get mistake statistics and teaching direction suggestions. (teacher, admin)"""

    _enforce_class_access(class_id, current_user)
    return ApiResponse(
        data=manager.get_teaching_analytics(class_id),
        message="Teaching analytics fetched successfully.",
    )


@router.post("/homework/assign", response_model=ApiResponse[AssignmentItem])
def assign_homework(
    payload: HomeworkAssign,
    current_user: User = Depends(require_role("teacher")),
) -> ApiResponse[AssignmentItem]:
    """Assign homework to a class. (teacher only)"""

    _enforce_class_access(payload.class_id, current_user)
    try:
        item = manager.create_assignment(payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=item, message="Homework assigned successfully.")


@router.get("/homework", response_model=ApiResponse[list[AssignmentItem]])
def list_homework(
    current_user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[AssignmentItem]]:
    return ApiResponse(
        data=manager.list_teacher_assignments(current_user.id, current_user.role),
        message="Homework fetched successfully.",
    )


@router.get("/students/me/homework", response_model=ApiResponse[list[AssignmentItem]])
def list_my_homework(
    current_user: User = Depends(require_role("student")),
) -> ApiResponse[list[AssignmentItem]]:
    return ApiResponse(
        data=manager.list_student_assignments(current_user.id),
        message="Homework fetched successfully.",
    )


@router.post(
    "/students/me/homework/{assignment_id}/submit", response_model=ApiResponse[SubmissionItem]
)
def submit_homework(
    assignment_id: int,
    payload: SubmissionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("student")),
) -> ApiResponse[SubmissionItem]:
    try:
        item = manager.submit_assignment(assignment_id, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item.practice_result and item.practice_result["status"] in ("pending", "failed"):
        from services.teacher_service.app.services.reinforcement_feedback import analyze_attempt
        background_tasks.add_task(analyze_attempt, item.practice_result["id"])
    return ApiResponse(data=item, message="Homework submitted successfully.")


@router.get(
    "/homework/{assignment_id}/submissions", response_model=ApiResponse[list[SubmissionItem]]
)
def list_homework_submissions(
    assignment_id: int,
    current_user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[SubmissionItem]]:
    try:
        items = manager.list_submissions(assignment_id, current_user.id, current_user.role)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=items, message="Submissions fetched successfully.")


@router.post("/homework/{submission_id}/review", response_model=ApiResponse[SubmissionItem])
def review_homework(
    submission_id: int,
    payload: ReviewPayload,
    current_user: User = Depends(require_role("teacher")),
) -> ApiResponse[SubmissionItem]:
    """Review one homework submission. (teacher only)"""

    try:
        item = manager.review_submission(submission_id, payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=item, message="Homework reviewed successfully.")


def _membership_call(function, *args):
    try:
        return function(*args)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/students/me/classes", response_model=ApiResponse[list[ClassItem]])
def my_classes(user: User = Depends(require_role("student"))):
    return ApiResponse(data=manager.list_my_classes(user.id))


@router.post("/students/me/classes/lookup", response_model=ApiResponse[ClassItem])
def lookup_class(payload: ClassJoin, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_membership_call(manager.lookup_invite, payload.invite_code))


@router.post("/students/me/classes/join", response_model=ApiResponse[ClassItem])
def join_class(payload: ClassJoin, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_membership_call(manager.join_class, payload.invite_code, user.id))


@router.get("/classes/{class_id}/members", response_model=ApiResponse[list[ClassMember]])
def class_members(class_id: int, user: User = Depends(require_role("teacher", "admin"))):
    return ApiResponse(data=_membership_call(manager.list_members, class_id, user.id, user.role))


@router.patch("/classes/{class_id}", response_model=ApiResponse[ClassItem])
def update_class(
    class_id: int, payload: ClassUpdate, user: User = Depends(require_role("teacher"))
):
    return ApiResponse(data=_membership_call(manager.update_class, class_id, payload, user.id))


@router.post("/classes/{class_id}/invite", response_model=ApiResponse[ClassItem])
def rotate_invite(class_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_membership_call(manager.rotate_invite, class_id, user.id))


@router.delete(
    "/classes/{class_id}/members/{student_id}", response_model=ApiResponse[list[ClassMember]]
)
def remove_member(class_id: int, student_id: int, user: User = Depends(require_role("teacher"))):
    return ApiResponse(data=_membership_call(manager.remove_member, class_id, student_id, user.id))
