"""Persistent models for learning check-ins and classroom attendance.

Three independent domains share these tables:

* self-directed study check-ins (``study_checkin_logs``)
* teacher-published check-in tasks and each occurrence's submission
  (``checkin_tasks`` / ``checkin_task_submissions``)
* classroom attendance sessions and records
  (``attendance_sessions`` / ``attendance_records``)

They are intentionally separate so completion rates never mix autonomous
check-ins, teacher task completion and classroom attendance.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base import Base
from common.models.learning import TimestampMixin


class PlatformDailyCheckin(TimestampMixin, Base):
    """One platform learning check-in per student per business day.

    It deliberately has no classroom/course/schedule reference: this is the
    student's own daily platform habit record, not classroom attendance.
    """

    __tablename__ = "platform_daily_checkins"
    __table_args__ = (
        UniqueConstraint("user_id", "checkin_date", name="uq_platform_checkin_user_day"),
        Index("ix_platform_checkin_user_date", "user_id", "checkin_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    checkin_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    checkin_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    timezone: Mapped[str] = mapped_column(
        String(40), default="Asia/Shanghai", server_default="Asia/Shanghai", nullable=False
    )
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reflection: Mapped[str] = mapped_column(Text, default="", nullable=False)


class ClassSession(TimestampMixin, Base):
    """Recurring weekly teaching session belonging to one classroom."""

    __tablename__ = "class_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    teacher_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    week_start: Mapped[str] = mapped_column(String(10), nullable=False)
    week_end: Mapped[str] = mapped_column(String(10), nullable=False)
    location: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    mode: Mapped[str] = mapped_column(
        String(16), default="offline", server_default="offline", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", nullable=False
    )


class PersonalSchedule(TimestampMixin, Base):
    """A student's recurring entry or private override of one classroom occurrence."""

    __tablename__ = "personal_schedules"
    __table_args__ = (
        UniqueConstraint("user_id", "source_session_id", "source_date", name="uq_personal_schedule_override"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=True)
    source_session_id: Mapped[int | None] = mapped_column(ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=True)
    source_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    topic: Mapped[str] = mapped_column(String(160))
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    week_start: Mapped[str] = mapped_column(String(10))
    week_end: Mapped[str] = mapped_column(String(10))
    location: Mapped[str] = mapped_column(String(160), default="")
    mode: Mapped[str] = mapped_column(String(16), default="offline")


class ClassScheduleException(TimestampMixin, Base):
    """One-off cancellation, reschedule or makeup for a session occurrence."""

    __tablename__ = "class_schedule_exceptions"
    __table_args__ = (
        UniqueConstraint("session_id", "date", name="uq_schedule_exception_session_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    teacher_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    new_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    new_start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    new_end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)


class CheckinTask(TimestampMixin, Base):
    """Teacher-published learning check-in task with a repeat schedule."""

    __tablename__ = "checkin_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id"), nullable=True, index=True
    )
    teacher_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), default="once", nullable=False)
    weekly_days: Mapped[list[int]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    due_time: Mapped[str] = mapped_column(
        String(5), default="23:59", server_default="23:59", nullable=False
    )
    allow_late: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    review_mode: Mapped[str] = mapped_column(
        String(8), default="manual", server_default="manual", nullable=False
    )
    require_attachment: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    knowledge_points: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="draft", server_default="draft", nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CheckinTaskSubmission(TimestampMixin, Base):
    """One student's submission for one concrete task occurrence."""

    __tablename__ = "checkin_task_submissions"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "student_user_id", "period_key", name="uq_checkin_task_period_student"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("checkin_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_key: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    period_due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attachment_ids: Mapped[list[int]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="submitted", server_default="submitted", nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    review_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CheckinSubmissionRevision(TimestampMixin, Base):
    """Append-only snapshot of a check-in submission before each change."""

    __tablename__ = "checkin_submission_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("checkin_task_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(30), default="update", nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AttendanceSession(TimestampMixin, Base):
    """One teacher-started classroom attendance window with a rotating code."""

    __tablename__ = "attendance_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id"), nullable=True, index=True
    )
    teacher_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    late_after_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open", nullable=False, index=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AttendanceRecord(TimestampMixin, Base):
    """Final attendance for one student in one session (unique per pair)."""

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("session_id", "student_user_id", name="uq_attendance_session_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="present", server_default="present", nullable=False, index=True
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(
        String(16), default="code", server_default="code", nullable=False
    )
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class CheckinAuditLog(TimestampMixin, Base):
    """Audit trail for manual attendance changes and task administration."""

    __tablename__ = "checkin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    before_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    after_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
