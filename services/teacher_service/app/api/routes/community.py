"""Authenticated discussion and notification routes shared by students and teachers."""

from fastapi import APIRouter, Depends, HTTPException

from common.dependencies import get_current_user
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.teacher import (
    DiscussionCreate,
    DiscussionItem,
    DiscussionReplyCreate,
    NotificationItem,
)
from services.teacher_service.app.services.teacher_manager import TeacherManager

router = APIRouter()
manager = TeacherManager()


@router.get("/discussions", response_model=ApiResponse[list[DiscussionItem]])
def list_discussions(current_user: User = Depends(get_current_user)) -> ApiResponse[list[DiscussionItem]]:
    return ApiResponse(
        data=manager.list_discussions(current_user.id, current_user.role),
        message="Discussions fetched successfully.",
    )


@router.post("/discussions", response_model=ApiResponse[DiscussionItem])
def create_discussion(
    payload: DiscussionCreate,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DiscussionItem]:
    try:
        item = manager.create_discussion(payload, current_user.id, current_user.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return ApiResponse(data=item, message="Discussion created successfully.")


@router.post("/discussions/{thread_id}/replies", response_model=ApiResponse[DiscussionItem])
def reply_discussion(
    thread_id: int,
    payload: DiscussionReplyCreate,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DiscussionItem]:
    try:
        item = manager.reply_discussion(thread_id, payload, current_user.id, current_user.role)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return ApiResponse(data=item, message="Reply created successfully.")


@router.get("/notifications", response_model=ApiResponse[list[NotificationItem]])
def list_notifications(current_user: User = Depends(get_current_user)) -> ApiResponse[list[NotificationItem]]:
    return ApiResponse(data=manager.list_notifications(current_user.id), message="Notifications fetched successfully.")


@router.patch("/notifications/{notification_id}/read", response_model=ApiResponse[NotificationItem])
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[NotificationItem]:
    try:
        item = manager.mark_notification_read(notification_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=item, message="Notification marked as read.")
