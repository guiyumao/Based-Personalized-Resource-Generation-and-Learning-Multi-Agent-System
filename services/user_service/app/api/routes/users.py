"""User service routes."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import get_db
from common.models.learning import User, UserProfile
from common.schemas.user import (
    LearnerProfileDashboard,
    ProfileChatRequest,
    ProfileChatResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserProfileRead,
    UserProfileUpdate,
    UserRegister,
    UserRead,
    to_user_profile_read,
    to_user_read,
)
from common.security.auth import create_access_token, hash_password, verify_password
from services.user_service.app.dependencies import get_current_user
from services.user_service.app.services.profile_builder import (
    PROFILE_DIMENSION_KEYS,
    ProfileBuilderService,
)

router = APIRouter()
settings = get_settings()


def _empty_learning_style(value: str | None) -> str:
    """Hide legacy placeholder learning-style values from API responses."""

    if not value or value == "VARK":
        return ""
    return value


def _new_empty_profile(user_id: int) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        mastery_json={},
        learning_style="",
        cognitive_abilities={},
        habits={},
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    """Create a platform user and initialize an empty learner profile."""

    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        email=payload.email,
    )
    db.add(user)
    db.flush()

    db.add(_new_empty_profile(user.id))
    db.commit()
    db.refresh(user)
    return to_user_read(user)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> TokenResponse:
    """Register a new user and immediately return a JWT token."""

    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        email=payload.email,
    )
    db.add(user)
    db.flush()

    db.add(_new_empty_profile(user.id))
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate a user and return a JWT token."""

    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)) -> UserRead:
    """Return the currently authenticated user."""

    return to_user_read(current_user)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)) -> UserRead:
    """Retrieve a user by ID."""

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return to_user_read(user)


@router.get("/{user_id}/profile", response_model=UserProfileRead)
def get_profile(user_id: int, db: Session = Depends(get_db)) -> UserProfileRead:
    """Retrieve a learner profile by user ID."""

    profile = db.get(UserProfile, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return to_user_profile_read(profile)


@router.put("/{user_id}/profile", response_model=UserProfileRead)
def update_profile(user_id: int, payload: UserProfileUpdate, db: Session = Depends(get_db)) -> UserProfileRead:
    """Manually update a learner profile."""

    service = ProfileBuilderService(db)
    try:
        profile = service.update_profile(user_id, payload.learning_style, payload.profile_dimensions)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_user_profile_read(profile)


@router.get("/{user_id}/profile/status", response_model=dict[str, object])
def get_profile_status(user_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Check whether the learner profile is complete enough to skip setup."""

    profile = db.get(UserProfile, user_id)
    if profile is None:
        return {
            "completed": False,
            "skipped": False,
            "dimensions_filled": 0,
            "total_dimensions": len(PROFILE_DIMENSION_KEYS),
        }

    habits = profile.habits if isinstance(profile.habits, dict) else {}
    raw_dimensions = habits.get("profile_dimensions")
    dimensions = raw_dimensions if isinstance(raw_dimensions, dict) else {}
    filled = sum(1 for key in PROFILE_DIMENSION_KEYS if dimensions.get(key))
    skipped = habits.get("profile_skipped", False)

    return {
        "completed": filled >= 3,
        "skipped": bool(skipped),
        "dimensions_filled": filled,
        "total_dimensions": len(PROFILE_DIMENSION_KEYS),
        "dimensions": {key: bool(dimensions.get(key)) for key in PROFILE_DIMENSION_KEYS},
    }


@router.post("/{user_id}/profile/skip", response_model=dict[str, object])
def skip_profile_setup(user_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Mark the profile setup as skipped by the user."""

    profile = db.get(UserProfile, user_id)
    if profile is None:
        profile = _new_empty_profile(user_id)
        db.add(profile)

    habits = profile.habits if isinstance(profile.habits, dict) else {}
    profile.habits = {**habits, "profile_skipped": True}
    db.commit()
    return {"skipped": True, "message": "画像构建已跳过，可稍后从工作台继续完善。"}


@router.post("/{user_id}/profile/chat", response_model=ProfileChatResponse)
def chat_profile(user_id: int, payload: ProfileChatRequest, db: Session = Depends(get_db)) -> ProfileChatResponse:
    """Build a learner profile through natural-language conversation."""

    service = ProfileBuilderService(db)
    try:
        return service.chat(user_id, payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/profile/dashboard", response_model=LearnerProfileDashboard)
def get_profile_dashboard(user_id: int, db: Session = Depends(get_db)) -> LearnerProfileDashboard:
    """Return learner dashboard data for the student workspace."""

    profile = db.get(UserProfile, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    empty_dashboard = LearnerProfileDashboard(
        user_id=user_id,
        learning_style=_empty_learning_style(profile.learning_style),
        mastery_overview=0,
        weekly_focus_minutes=0,
        habit_summary="",
        radar_metrics=[],
        heatmap=[],
    )

    try:
        response = httpx.get(
            f"{settings.evaluation_service_url}/evaluation/profiles/{user_id}/snapshot",
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return empty_dashboard
        data["learning_style"] = _empty_learning_style(data.get("learning_style") or profile.learning_style)
        return LearnerProfileDashboard(**data)
    except Exception:
        return empty_dashboard


@router.post("/{user_id}/token")
def create_user_token(user_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    """Issue a JWT token for a known user."""

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"access_token": create_access_token(str(user.id)), "token_type": "bearer"}
