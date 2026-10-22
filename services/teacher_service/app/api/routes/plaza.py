"""Student classroom plaza: browse joinable classes and self-enroll.

Auth classification:
- GET  /classrooms/plaza            : PROTECTED (student)
- POST /classrooms/{id}/join       : PROTECTED (student)
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from common.dependencies import require_role
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.teacher import ClassItem, PlazaClassItem
from services.teacher_service.app.services.teacher_manager import TeacherManager

router = APIRouter()
manager = TeacherManager()


def _call(function, *args):
    try:
        return function(*args)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/classrooms/plaza", response_model=ApiResponse[list[PlazaClassItem]])
def list_plaza(
    query: str = Query(default="", max_length=100),
    subject: str = Query(default="", max_length=100),
    user: User = Depends(require_role("student")),
):
    """Search public classes or exactly match a supplied invite, without returning codes."""

    return ApiResponse(data=manager.list_plaza(user.id, query, subject))


@router.get("/classrooms/mine", response_model=ApiResponse[list[ClassItem]])
def my_classrooms(user: User = Depends(require_role("student"))):
    return ApiResponse(data=manager.list_my_classes(user.id))


@router.get("/classrooms/{class_id}", response_model=ApiResponse[PlazaClassItem])
def classroom_detail(class_id: int, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_call(manager.get_public_class, class_id, user.id))


@router.post("/classrooms/{class_id}/join", response_model=ApiResponse[ClassItem])
def join_from_plaza(class_id: int, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_call(manager.join_plaza_class, class_id, user.id))


@router.post("/classrooms/{class_id}/leave", response_model=ApiResponse[ClassItem])
def leave_classroom(class_id: int, user: User = Depends(require_role("student"))):
    return ApiResponse(data=_call(manager.leave_class, class_id, user.id))
