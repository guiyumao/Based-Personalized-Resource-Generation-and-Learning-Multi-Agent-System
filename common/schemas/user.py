"""User-related API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


PROFILE_DIMENSION_KEYS = (
    "knowledgeBase",
    "cognitiveStyle",
    "errorPreference",
    "learningSpeed",
    "interestDirection",
    "goalOrientation",
)


def sanitize_profile_dimensions(raw_dimensions: Any) -> dict[str, str]:
    """Filter empty or obviously invalid stored learner-profile dimensions."""

    if not isinstance(raw_dimensions, dict):
        return {}

    cleaned: dict[str, str] = {}
    for key, raw_value in raw_dimensions.items():
        if key not in PROFILE_DIMENSION_KEYS:
            continue
        value = str(raw_value).strip()
        if not value:
            continue
        if _looks_like_bulk_profile_dump(value):
            continue
        cleaned[str(key)] = value
    return cleaned


def _looks_like_bulk_profile_dump(value: str) -> bool:
    """Detect malformed dimension values that are actually pasted multi-dimension payloads."""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if "我想一次补充画像多维度" in normalized:
        return True

    marker_count = sum(
        marker in normalized
        for marker in ("知识基础", "认知风格", "易错偏好", "学习节奏", "兴趣方向", "目标导向")
    )
    if marker_count >= 2:
        return True

    return normalized.count("\n") >= 2 and "：" in normalized


class UserCreate(BaseModel):
    """Payload used to create a new user account."""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    role: str = "student"
    email: str | None = None


class UserRegister(BaseModel):
    """Payload used to register a new user and return a token."""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    role: str = "student"
    email: str | None = None


class UserRead(BaseModel):
    """Public user response schema."""

    id: int
    username: str
    role: str
    email: str | None
    created_at: datetime


class UserProfileRead(BaseModel):
    """Learner profile response schema."""

    user_id: int
    mastery_json: dict[str, Any]
    learning_style: str
    cognitive_abilities: dict[str, Any]
    habits: dict[str, Any]
    profile_dimensions: dict[str, str] = Field(default_factory=dict)


class UserProfileUpdate(BaseModel):
    """Manual learner profile update payload."""

    learning_style: str | None = None
    profile_dimensions: dict[str, str] = Field(default_factory=dict)


class ProfileChatRequest(BaseModel):
    """Payload for conversational learner-profile building."""

    message: str = Field(default="", max_length=1000)


class ProfileChatResponse(BaseModel):
    """Structured result for one profile-building conversation turn."""

    reply: str
    profile_updates: dict[str, str] = Field(default_factory=dict)
    profile_completeness: dict[str, str]
    estimated_remaining_rounds: int


class LearnerRadarMetric(BaseModel):
    """One metric entry shown in the learner radar board."""

    dimension: str
    score: int


class LearnerHeatmapCell(BaseModel):
    """One knowledge mastery cell shown in the learner heatmap."""

    knowledge_point: str
    mastery: int


class LearnerProfileDashboard(BaseModel):
    """Aggregated learner dashboard payload for the student workspace."""

    user_id: int
    learning_style: str
    mastery_overview: int
    weekly_focus_minutes: int
    habit_summary: str
    radar_metrics: list[LearnerRadarMetric]
    heatmap: list[LearnerHeatmapCell]


class UserLogin(BaseModel):
    """Payload used to log into the system."""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    """JWT token response schema."""

    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str


def to_user_read(user: object) -> UserRead:
    """Convert an ORM-like user object to `UserRead`."""

    return UserRead(
        id=getattr(user, "id"),
        username=getattr(user, "username"),
        role=getattr(user, "role"),
        email=getattr(user, "email"),
        created_at=getattr(user, "created_at"),
    )


def to_user_profile_read(profile: object) -> UserProfileRead:
    """Convert an ORM-like user profile object to `UserProfileRead`."""

    habits = getattr(profile, "habits")
    profile_dimensions: dict[str, str] = {}
    if isinstance(habits, dict):
        profile_dimensions = sanitize_profile_dimensions(habits.get("profile_dimensions"))

    return UserProfileRead(
        user_id=getattr(profile, "user_id"),
        mastery_json=getattr(profile, "mastery_json"),
        learning_style=getattr(profile, "learning_style"),
        cognitive_abilities=getattr(profile, "cognitive_abilities"),
        habits=habits,
        profile_dimensions=profile_dimensions,
    )
