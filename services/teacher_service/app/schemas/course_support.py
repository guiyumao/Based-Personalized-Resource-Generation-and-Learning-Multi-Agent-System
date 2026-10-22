"""Teacher-controlled resource and reinforcement contracts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeliveryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=80)
    student_user_id: int | None = None
    resource_id: int | None = None
    title: str = Field(default="", max_length=160)
    content: str = Field(default="", max_length=60000)
    knowledge_points: list[str] = Field(default_factory=list, max_length=20)


class DeliveryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    class_id: int
    student_user_id: int | None
    title: str
    content: str
    knowledge_points: list[str]
    resource_id: int | None
    created_at: datetime


class ReinforcementCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=80)
    student_user_id: int
    delivery_ids: list[int] = Field(min_length=1, max_length=5)
    question_count: int = Field(default=3, ge=1, le=10)
    teacher_note: str = Field(default="", max_length=1500)


class ReinforcementQuestion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    knowledge_point: str = Field(min_length=1, max_length=160)
    question_type: Literal["choice", "short_answer"]
    prompt: str = Field(min_length=8, max_length=6000)
    options: list[str] = Field(default_factory=list, max_length=6)
    answer: str = Field(min_length=1, max_length=3000)
    analysis: str = Field(min_length=1, max_length=6000)
    evidence_ids: list[int] = Field(default_factory=list, max_length=20)


class DraftEdit(BaseModel):
    questions: list[ReinforcementQuestion] = Field(min_length=1, max_length=10)
    rationale: str = Field(default="", max_length=6000)


class DraftPublish(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def future_due_date(cls, value):
        from datetime import UTC
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("截止时间必须包含时区")
        result = value.astimezone(UTC).replace(tzinfo=None)
        if result <= datetime.now(UTC).replace(tzinfo=None):
            raise ValueError("截止时间必须晚于当前时间")
        return result
