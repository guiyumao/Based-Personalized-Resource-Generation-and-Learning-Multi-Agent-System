"""User service routes."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import get_db
from common.models.learning import User, UserProfile
from common.schemas.user import (
    LearnerHeatmapCell,
    LearnerProfileDashboard,
    LearnerRadarMetric,
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
from services.user_service.app.services.profile_analysis import ProfileAnalysisService
from services.user_service.app.services.profile_builder import (
    PROFILE_DIMENSION_KEYS,
    PROFILE_DIMENSION_LABELS,
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
    """Return learner dashboard data for the student workspace.

    Profile-builder data (learning_style, habits, profile_dimensions) is
    read directly from the database.  Exercise-derived metrics (mastery,
    radar, heatmap) are fetched from the evaluation-service when available."""

    profile = db.get(UserProfile, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    # ── Always-populated fields from the profile builder ──────────
    learning_style = _empty_learning_style(profile.learning_style)
    habits = profile.habits if isinstance(profile.habits, dict) else {}
    raw_dimensions = habits.get("profile_dimensions")
    profile_dimensions = raw_dimensions if isinstance(raw_dimensions, dict) else {}

    # Build habit summary from filled dimensions
    filled_labels = [
        PROFILE_DIMENSION_LABELS.get(k, k)
        for k in PROFILE_DIMENSION_KEYS
        if profile_dimensions.get(k)
    ]
    habit_summary_parts: list[str] = []
    if filled_labels:
        habit_summary_parts.append(f"已记录画像维度：{'、'.join(filled_labels)}")
    if _empty_learning_style(profile.learning_style):
        cognitive_map = {"visual": "视觉型", "reading": "文本型", "auditory": "听觉型", "kinesthetic": "动手实践型"}
        style_label = cognitive_map.get(profile.learning_style, profile.learning_style)
        habit_summary_parts.append(f"学习风格：{style_label}")
    habit_summary = "；".join(habit_summary_parts) if habit_summary_parts else ""

    # Build radar metrics from profile dimensions (always available)
    radar_metrics: list[LearnerRadarMetric] = []
    if learning_style:
        radar_metrics.append(LearnerRadarMetric(dimension="学习画像已构建", score=100))
    for key in PROFILE_DIMENSION_KEYS:
        if profile_dimensions.get(key):
            label = PROFILE_DIMENSION_LABELS.get(key, key)
            # Assign a baseline score — dimensions are "known" but not yet measured via exercises
            radar_metrics.append(LearnerRadarMetric(dimension=label, score=50))

    base_dashboard = LearnerProfileDashboard(
        user_id=user_id,
        learning_style=learning_style,
        mastery_overview=0,
        weekly_focus_minutes=0,
        habit_summary=habit_summary,
        radar_metrics=radar_metrics,
        heatmap=[],
    )

    # ── Augment with evaluation-service data when available ───────
    try:
        response = httpx.get(
            f"{settings.evaluation_service_url}/evaluation/profiles/{user_id}/snapshot",
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
        eval_data = payload.get("data") or {}
        if not isinstance(eval_data, dict):
            return base_dashboard

        # Merge: evaluation data overrides base, but keep profile-builder
        # learning_style if eval doesn't have a real one
        eval_ls = _empty_learning_style(eval_data.get("learning_style"))
        merged_style = eval_ls or learning_style

        eval_radar = eval_data.get("radar_metrics") or []
        merged_radar = radar_metrics if isinstance(eval_radar, list) and eval_radar else radar_metrics

        eval_heatmap = eval_data.get("heatmap") or []

        return LearnerProfileDashboard(
            user_id=user_id,
            learning_style=merged_style,
            mastery_overview=eval_data.get("mastery_overview", 0),
            weekly_focus_minutes=eval_data.get("weekly_focus_minutes", 0),
            habit_summary=eval_data.get("habit_summary") or habit_summary,
            radar_metrics=merged_radar,
            heatmap=eval_heatmap if isinstance(eval_heatmap, list) else [],
        )
    except Exception:
        return base_dashboard


# ── Profile deep-analysis endpoints ─────────────────────────────


@router.get("/{user_id}/profile/analysis", response_model=dict[str, object])
def get_profile_analysis(user_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Return cached analysis or launch async generation."""
    service = ProfileAnalysisService(db)
    try:
        return service.get_or_generate(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/profile/analysis/status", response_model=dict[str, object])
def get_analysis_status(user_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Poll for analysis generation progress."""
    service = ProfileAnalysisService(db)
    return service.get_status(user_id)


@router.post("/{user_id}/profile/analysis/refresh", response_model=dict[str, object])
def refresh_profile_analysis(user_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Force-regenerate the profile analysis."""
    service = ProfileAnalysisService(db)
    try:
        return service.force_refresh(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/token")
def create_user_token(user_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    """Issue a JWT token for a known user."""

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"access_token": create_access_token(str(user.id)), "token_type": "bearer"}
