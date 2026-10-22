"""Paged inbox shared by authenticated student/teacher layouts."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from common.db.session import get_db
from common.dependencies import get_current_user, require_role
from common.models.learning import AssistantTask, KnowledgeBuildTask, Notification
from common.notifications import publish, serialize, target_path, visible

router = APIRouter()


class Publication(BaseModel):
    request_key: str = Field(min_length=8, max_length=80)
    scope: Literal["students", "teachers", "student", "teacher", "class", "course"]
    target_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=10000)
    type: Literal["announcement", "maintenance", "account", "course"] = "announcement"


@router.get("/inbox")
def inbox(
    page: int = Query(1, ge=1),
    size: int = Query(8, ge=1, le=50),
    unread: bool = False,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    query = visible(db, user)
    unread_count = query.filter_by(is_read=False).count()
    if unread:
        query = query.filter_by(is_read=False)
    return {
        "data": {
            "items": [
                serialize(db, n)
                for n in query.order_by(Notification.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            ],
            "total": query.count(),
            "unread_count": unread_count,
        }
    }


@router.get("/unread-count")
def unread_count(user=Depends(get_current_user), db=Depends(get_db)):
    return {"data": {"unread_count": visible(db, user).filter_by(is_read=False).count()}}


@router.post("/read-all")
def read_all(user=Depends(get_current_user), db=Depends(get_db)):
    visible(db, user).filter_by(is_read=False).update(
        {"is_read": True, "read_at": datetime.utcnow()}, synchronize_session=False
    )
    db.commit()
    return {"data": {"unread_count": 0}}


@router.post("/publish")
def publication(
    payload: Publication, user=Depends(require_role("admin", "teacher")), db=Depends(get_db)
):
    if not payload.title.strip() or not payload.content.strip():
        raise HTTPException(422, "标题和正文不能为空")
    try:
        try:
            result = publish(db, user, payload)
        except IntegrityError:
            db.rollback()
            result = publish(db, user, payload)
        return {"data": result}
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{notification_id}/detail")
def detail(notification_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    item = visible(db, user).filter_by(id=notification_id).first()
    if item is None:
        raise HTTPException(404, "消息或关联业务已失效，或当前没有访问权限")
    data = {**serialize(db, item), "target_path": target_path(db, item, user)}
    model = (
        AssistantTask
        if item.related_type == "task"
        else KnowledgeBuildTask
        if item.related_type == "knowledge_task"
        else None
    )
    if item.related_type == "discussion":
        from common.models.learning import DiscussionThread
        from services.teacher_service.app.services.teacher_manager import TeacherManager

        data["discussion"] = (
            TeacherManager()
            ._discussion_to_item(db, db.get(DiscussionThread, item.related_id))
            .model_dump()
        )
    if model:
        task = db.get(model, item.related_id)
        data["content"] += f"\n当前任务状态：{task.status}；{task.current_step}"
    return {"data": data}
