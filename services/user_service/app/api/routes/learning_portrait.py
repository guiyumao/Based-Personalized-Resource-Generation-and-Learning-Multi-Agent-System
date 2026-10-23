"""Self-reported style preferences alongside the existing evidence profile."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user, require_self_or_admin
from common.models.learning import AuditLog, User, UserProfile
from common.schemas.user import PROFILE_DIMENSION_KEYS, sanitize_profile_dimensions
from services.user_service.app.services.learning_style_inference import (
    infer_learning_style,
    inference_state,
    merged_axes,
    style_source_text,
)
from services.user_service.app.services.zhishu_profile import build_user_zhishu_profile

router = APIRouter()
Axis = Literal["processing", "perception", "input", "understanding"]


class PortraitEdit(BaseModel):
    expected_updated_at: datetime | None = None
    axes: dict[Axis, Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] | None] = Field(
        default_factory=dict
    )
    dimensions: dict[str, Annotated[str, Field(max_length=1500)]] = Field(default_factory=dict)


class PortraitInference(BaseModel):
    force: bool = False


def snapshot(db: Session, user_id: int) -> dict:
    profile = db.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(
            user_id=user_id, mastery_json={}, cognitive_abilities={}, habits={}, learning_style=""
        )
    habits = profile.habits if isinstance(profile.habits, dict) else {}
    axes = merged_axes(profile)
    return {
        "user_id": user_id,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        "axes": axes,
        "dimensions": sanitize_profile_dimensions(habits.get("profile_dimensions")),
        "dimension_sources": habits.get("profile_fact_sources", {}),
        "behavior_profile": build_user_zhishu_profile(db, profile),
        "style_source": style_source_text(axes),
        "inference": inference_state(db, user_id, profile),
    }


@router.get("/users/{user_id}/learning-portrait")
def read_portrait(
    user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_self_or_admin(user_id, user)
    if db.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    return snapshot(db, user_id)


@router.post("/users/{user_id}/learning-portrait/infer")
def infer_portrait(
    user_id: int,
    payload: PortraitInference,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Let the model infer the style axes from the evidence already collected."""

    require_self_or_admin(user_id, user)
    if db.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    result = infer_learning_style(db, user_id, force=payload.force)
    db.expire_all()
    return {**result, "snapshot": snapshot(db, user_id)}


@router.put("/users/{user_id}/learning-portrait")
def edit_portrait(
    user_id: int,
    payload: PortraitEdit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_self_or_admin(user_id, user)
    if db.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    if set(payload.dimensions) - set(PROFILE_DIMENSION_KEYS):
        raise HTTPException(422, "Unknown profile dimension")
    profile = db.get(UserProfile, user_id)
    if profile is not None and (
        payload.expected_updated_at is None
        or profile.updated_at != payload.expected_updated_at.replace(tzinfo=None)
    ):
        raise HTTPException(409, "画像已更新，请刷新后再编辑")
    habits = dict(profile.habits or {}) if profile else {}
    axes = dict(habits.get("learning_style_axes") or {})
    for key, value in payload.axes.items():
        if value is None:
            axes.pop(key, None)
        else:
            axes[key] = value
    dimensions = dict(habits.get("profile_dimensions") or {})
    sources = dict(habits.get("profile_fact_sources") or {})
    for key, value in payload.dimensions.items():
        if value.strip():
            dimensions[key] = value.strip()
            sources[key] = "user_reported"
        else:
            dimensions.pop(key, None)
            sources.pop(key, None)
    habits.update(
        learning_style_axes=axes, profile_dimensions=dimensions, profile_fact_sources=sources
    )
    stamped = datetime.utcnow()
    if profile is None:
        db.add(
            UserProfile(
                user_id=user_id,
                habits=habits,
                mastery_json={},
                cognitive_abilities={},
                learning_style="",
                updated_at=stamped,
            )
        )
    else:
        result = db.execute(
            update(UserProfile)
            .where(UserProfile.user_id == user_id, UserProfile.updated_at == profile.updated_at)
            .values(habits=habits, updated_at=stamped, profile_analysis=None)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "画像已更新，请刷新后再编辑")
    db.add(
        AuditLog(
            actor_user_id=user.id,
            level="INFO",
            event="profile.preferences.updated",
            message=f"user={user_id} axes={','.join(payload.axes)} dimensions={','.join(payload.dimensions)}",
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "画像已更新，请刷新后再编辑") from exc
    db.expire_all()
    return snapshot(db, user_id)
