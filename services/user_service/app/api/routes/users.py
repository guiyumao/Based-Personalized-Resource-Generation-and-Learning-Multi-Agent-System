"""User service routes."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import get_db
from common.models.learning import User, UserProfile
from common.schemas.user import (
    LearnerProfileDashboard,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserProfileRead,
    UserRegister,
    UserRead,
    to_user_profile_read,
    to_user_read,
)
from common.security.auth import create_access_token, hash_password, verify_password
from services.user_service.app.dependencies import get_current_user

router = APIRouter()
settings = get_settings()


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

    profile = UserProfile(
        user_id=user.id,
        mastery_json={},
        learning_style="VARK",
        cognitive_abilities={},
        habits={},
    )
    db.add(profile)
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

    profile = UserProfile(
        user_id=user.id,
        mastery_json={},
        learning_style="VARK",
        cognitive_abilities={},
        habits={},
    )
    db.add(profile)
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


@router.get("/{user_id}/profile/dashboard", response_model=LearnerProfileDashboard)
def get_profile_dashboard(user_id: int, db: Session = Depends(get_db)) -> LearnerProfileDashboard:
    """Return learner dashboard data for the student workspace."""

    profile = db.get(UserProfile, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    fallback = LearnerProfileDashboard(
        user_id=user_id,
        learning_style=profile.learning_style or "VARK",
        mastery_overview=62,
        weekly_focus_minutes=180,
        habit_summary="近期主要集中在晚间学习，建议维持固定节奏。",
        radar_metrics=[
            {"dimension": "知识掌握", "score": 62},
            {"dimension": "逻辑分析", "score": 68},
            {"dimension": "作答稳定性", "score": 64},
            {"dimension": "完成速度", "score": 58},
            {"dimension": "复盘反思", "score": 71},
        ],
        heatmap=[
            {"knowledge_point": "Python 循环", "mastery": 62},
            {"knowledge_point": "条件判断", "mastery": 57},
            {"knowledge_point": "列表与字典", "mastery": 69},
            {"knowledge_point": "函数封装", "mastery": 55},
            {"knowledge_point": "综合应用", "mastery": 48},
        ],
    )

    try:
        response = httpx.get(
            f"{settings.evaluation_service_url}/evaluation/profiles/{user_id}/snapshot",
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
        return LearnerProfileDashboard(**payload["data"])
    except Exception:
        return fallback


@router.post("/{user_id}/token")
def create_user_token(user_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    """Issue a JWT token for a known user."""

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"access_token": create_access_token(str(user.id)), "token_type": "bearer"}
