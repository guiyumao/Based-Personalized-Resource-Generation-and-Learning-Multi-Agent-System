"""User-related API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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

    return UserProfileRead(
        user_id=getattr(profile, "user_id"),
        mastery_json=getattr(profile, "mastery_json"),
        learning_style=getattr(profile, "learning_style"),
        cognitive_abilities=getattr(profile, "cognitive_abilities"),
        habits=getattr(profile, "habits"),
    )
