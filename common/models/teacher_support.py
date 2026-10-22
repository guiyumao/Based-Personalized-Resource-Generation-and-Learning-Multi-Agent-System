"""Teacher-owned resource deliveries and personalized homework drafts."""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base import Base
from common.models.learning import TimestampMixin


class CourseResourceDelivery(TimestampMixin, Base):
    __tablename__ = "course_resource_deliveries"
    __table_args__ = (UniqueConstraint("teacher_user_id", "request_id", name="uq_course_delivery_request"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), index=True)
    teacher_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    student_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    request_id: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    resource_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    knowledge_points: Mapped[list[str]] = mapped_column(JSON, default=list)


class ReinforcementDraft(TimestampMixin, Base):
    __tablename__ = "reinforcement_drafts"
    __table_args__ = (UniqueConstraint("teacher_user_id", "request_id", name="uq_reinforcement_request"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), index=True)
    teacher_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    student_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(80))
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    resource_snapshots: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="generating")
    error: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(160), default="")
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("assignments.id"), nullable=True, unique=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReinforcementAttempt(TimestampMixin, Base):
    __tablename__ = "reinforcement_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("reinforcement_drafts.id"), unique=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("assignment_submissions.id"), unique=True)
    student_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    answers: Mapped[list[str]] = mapped_column(JSON)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    analysis_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    analysis: Mapped[str] = mapped_column(Text, default="")
    recommendations: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_name: Mapped[str] = mapped_column(String(160), default="")
    error: Mapped[str] = mapped_column(Text, default="")
