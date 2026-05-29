"""Teacher class management routes."""

from fastapi import APIRouter

from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.teacher import (
    ClassCreate,
    ClassItem,
    HomeworkAssign,
    ReviewPayload,
    StudentLearningDetail,
    StudentInsight,
)
from services.teacher_service.app.services.teacher_manager import TeacherManager

router = APIRouter()
manager = TeacherManager()


@router.get("/classes", response_model=ApiResponse[list[ClassItem]])
def list_classes() -> ApiResponse[list[ClassItem]]:
    """List all classes."""

    return ApiResponse(data=manager.list_classes(), message="Classes fetched successfully.")


@router.post("/classes", response_model=ApiResponse[ClassItem])
def create_class(payload: ClassCreate) -> ApiResponse[ClassItem]:
    """Create a new class."""

    return ApiResponse(data=manager.create_class(payload), message="Class created successfully.")


@router.get("/classes/{class_id}/progress", response_model=ApiResponse[dict[str, object]])
def get_class_progress(class_id: int) -> ApiResponse[dict[str, object]]:
    """Get class progress overview."""

    return ApiResponse(
        data=manager.get_student_progress(class_id),
        message="Class progress fetched successfully.",
    )


@router.get("/classes/{class_id}/insights", response_model=ApiResponse[list[StudentInsight]])
def get_class_insights(class_id: int) -> ApiResponse[list[StudentInsight]]:
    """Get student insights for one class."""

    return ApiResponse(
        data=manager.list_student_insights(class_id),
        message="Class student insights fetched successfully.",
    )


@router.get("/classes/{class_id}/students/{user_id}", response_model=ApiResponse[StudentLearningDetail])
async def get_student_learning_detail(class_id: int, user_id: int) -> ApiResponse[StudentLearningDetail]:
    """Get one student's detailed mistake notebook and learning reports."""

    return ApiResponse(
        data=await manager.get_student_learning_detail(class_id, user_id),
        message="Student learning detail fetched successfully.",
    )


@router.post("/homework/assign", response_model=ApiResponse[dict[str, object]])
def assign_homework(payload: HomeworkAssign) -> ApiResponse[dict[str, object]]:
    """Assign homework to a class."""

    return ApiResponse(
        data=payload.model_dump(),
        message="Homework assigned successfully.",
    )


@router.post("/homework/{submission_id}/review", response_model=ApiResponse[dict[str, object]])
def review_homework(submission_id: int, payload: ReviewPayload) -> ApiResponse[dict[str, object]]:
    """Review one homework submission."""

    return ApiResponse(
        data={"submission_id": submission_id, **payload.model_dump()},
        message="Homework reviewed successfully.",
    )
