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

from fastapi import APIRouter, Depends, HTTPException

from common.dependencies import require_role
from common.dependencies import get_current_user
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.teacher import (
    ClassCreate,
    ClassItem,
    HomeworkAssign,
    ReviewPayload,
    StudentLearningDetail,
    StudentInsight,
    TeacherTeachingAnalytics,
    TeachingScopeCreate,
    TeachingScopeItem,
)
from services.teacher_service.app.services.teacher_manager import TeacherManager

router = APIRouter()
manager = TeacherManager()


@router.get("/classes", response_model=ApiResponse[list[ClassItem]])
def list_classes(
    _user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[ClassItem]]:
    """List all classes. (teacher, admin)"""

    return ApiResponse(data=manager.list_classes(), message="Classes fetched successfully.")


@router.post("/classes", response_model=ApiResponse[ClassItem])
def create_class(
    payload: ClassCreate,
    _user: User = Depends(require_role("teacher")),
) -> ApiResponse[ClassItem]:
    """Create a new class. (teacher only)"""

    return ApiResponse(data=manager.create_class(payload), message="Class created successfully.")


@router.get("/classes/{class_id}/progress", response_model=ApiResponse[dict[str, object]])
def get_class_progress(
    class_id: int,
    _user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[dict[str, object]]:
    """Get class progress overview. (teacher, admin)"""

    return ApiResponse(
        data=manager.get_student_progress(class_id),
        message="Class progress fetched successfully.",
    )


@router.get("/classes/{class_id}/insights", response_model=ApiResponse[list[StudentInsight]])
def get_class_insights(
    class_id: int,
    _user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[StudentInsight]]:
    """Get student insights for one class. (teacher, admin)"""

    return ApiResponse(
        data=manager.list_student_insights(class_id),
        message="Class student insights fetched successfully.",
    )


@router.get("/classes/{class_id}/students/{user_id}", response_model=ApiResponse[StudentLearningDetail])
async def get_student_learning_detail(
    class_id: int,
    user_id: int,
    _user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[StudentLearningDetail]:
    """Get one student's detailed mistake notebook and learning reports. (teacher, admin)"""

    try:
        detail = await manager.get_student_learning_detail(class_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ApiResponse(
        data=detail,
        message="Student learning detail fetched successfully.",
    )


@router.get("/classes/{class_id}/teaching-scopes", response_model=ApiResponse[list[TeachingScopeItem]])
def list_teaching_scopes(
    class_id: int,
    _user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[TeachingScopeItem]]:
    """List teacher-defined scopes for one class. (teacher, admin)"""

    return ApiResponse(
        data=manager.list_teaching_scopes(class_id),
        message="Teaching scopes fetched successfully.",
    )


@router.post("/teaching-scopes", response_model=ApiResponse[TeachingScopeItem])
def create_teaching_scope(
    payload: TeachingScopeCreate,
    _user: User = Depends(require_role("teacher")),
) -> ApiResponse[TeachingScopeItem]:
    """Define learning scope, direction, and courseware for students. (teacher only)"""

    return ApiResponse(
        data=manager.create_teaching_scope(payload),
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


@router.get("/students/{user_id}/teaching-scopes", response_model=ApiResponse[list[TeachingScopeItem]])
def list_student_teaching_scopes(
    user_id: int,
    _user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[list[TeachingScopeItem]]:
    """List teacher-defined scopes visible to one learner. (teacher, admin)"""

    return ApiResponse(
        data=manager.list_student_teaching_scopes(user_id),
        message="Student teaching scopes fetched successfully.",
    )


@router.get("/classes/{class_id}/teaching-analytics", response_model=ApiResponse[TeacherTeachingAnalytics])
def get_teaching_analytics(
    class_id: int,
    _user: User = Depends(require_role("teacher", "admin")),
) -> ApiResponse[TeacherTeachingAnalytics]:
    """Get mistake statistics and teaching direction suggestions. (teacher, admin)"""

    return ApiResponse(
        data=manager.get_teaching_analytics(class_id),
        message="Teaching analytics fetched successfully.",
    )


@router.post("/homework/assign", response_model=ApiResponse[dict[str, object]])
def assign_homework(
    payload: HomeworkAssign,
    _user: User = Depends(require_role("teacher")),
) -> ApiResponse[dict[str, object]]:
    """Assign homework to a class. (teacher only)"""

    return ApiResponse(
        data=payload.model_dump(),
        message="Homework assigned successfully.",
    )


@router.post("/homework/{submission_id}/review", response_model=ApiResponse[dict[str, object]])
def review_homework(
    submission_id: int,
    payload: ReviewPayload,
    _user: User = Depends(require_role("teacher")),
) -> ApiResponse[dict[str, object]]:
    """Review one homework submission. (teacher only)"""

    return ApiResponse(
        data={"submission_id": submission_id, **payload.model_dump()},
        message="Homework reviewed successfully.",
    )
