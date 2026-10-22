"""Core SQLAlchemy models for the learning system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base import Base


class TimestampMixin:
    """Reusable timestamp fields."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class User(TimestampMixin, Base):
    """Platform user account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="student", nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    profile: Mapped[UserProfile] = relationship(back_populates="user", uselist=False)
    learning_paths: Mapped[list[LearningPath]] = relationship(back_populates="user")
    answer_records: Mapped[list[AnswerRecord]] = relationship(back_populates="user")
    reports: Mapped[list[LearningReport]] = relationship(back_populates="user")


class UserProfile(Base):
    """Four-dimensional learner profile."""

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    mastery_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    learning_style: Mapped[str] = mapped_column(String(20), default="")
    cognitive_abilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    habits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    profile_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    user: Mapped[User] = relationship(back_populates="profile")


class KnowledgePoint(Base):
    """Knowledge point metadata."""

    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    importance: Mapped[int] = mapped_column(Integer, default=1)
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chapter: Mapped[str] = mapped_column(String(160), nullable=False, default="", server_default="")
    aliases_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    objectives_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    prerequisites_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    construction_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PLANNED", server_default="PLANNED")


class KnowledgeRelation(Base):
    """Directed relation between knowledge points."""

    __tablename__ = "knowledge_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), nullable=False)
    to_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)


class Resource(TimestampMixin, Base):
    """Generated or curated learning resource."""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(20), default="markdown")
    knowledge_point_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_points.id"))
    generated_for_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    crawl_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default="pending")
    language: Mapped[str | None] = mapped_column(String(10), nullable=True, default="zh")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_status: Mapped[str] = mapped_column(String(20), default="generated")
    audit_status: Mapped[str] = mapped_column(String(20), default="pending")
    publish_status: Mapped[str] = mapped_column(String(20), default="draft")
    audit_reason: Mapped[str] = mapped_column(Text, default="")
    # Machine-readable payload for the structured resource types (``mind_map``,
    # ``code_case``, ``video_script``). ``content`` keeps the human-readable
    # Markdown rendering; this column keeps the nodes/edges/chapters plus the
    # deterministic validation report so the UI can render the real structure and
    # its verification status instead of re-parsing prose. NULL for every
    # resource kind written before this column existed.
    structured_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistant_operation_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    knowledge_versions_json: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    knowledge_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")


class ResourceInteraction(Base):
    """Authenticated learner interaction used for resource recommendations."""

    __tablename__ = "resource_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    knowledge_point: Mapped[str] = mapped_column(String(100), default="", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        index=True,
    )


class StudySession(Base):
    """One server-owned activity cursor per learner, shared by every tab/device."""

    __tablename__ = "study_sessions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tab_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class StudyActivity(Base):
    """Credited, non-overlapping server-time intervals; never a page-open timer."""

    __tablename__ = "study_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    page: Mapped[str] = mapped_column(String(40), nullable=False)


class LearningPath(TimestampMixin, Base):
    """Personalized learning path."""

    __tablename__ = "learning_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    path_data_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")

    user: Mapped[User] = relationship(back_populates="learning_paths")
    tasks: Mapped[list[LearningTask]] = relationship(back_populates="path")


class CoordinationTask(TimestampMixin, Base):
    """Async coordination request (RabbitMQ-backed) for long agent workflows.

    The browser submits the request once, polls this row, and may navigate away
    while the worker keeps running; the result is stored here so a reload can
    still pick it up.
    """

    __tablename__ = "coordination_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    worker_id: Mapped[str] = mapped_column(String(80), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LearningTask(Base):
    """Task item within a learning path."""

    __tablename__ = "learning_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path_id: Mapped[int] = mapped_column(ForeignKey("learning_paths.id"), nullable=False)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    path: Mapped[LearningPath] = relationship(back_populates="tasks")


class LearningKnowledgeGap(TimestampMixin, Base):
    """Learner-requested catalog/coverage gap; never an approved knowledge node."""
    __tablename__ = "learning_knowledge_gaps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    request_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge_point: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="REQUESTED")
    knowledge_task_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_build_tasks.id"), nullable=True)


class LearningContext(TimestampMixin, Base):
    """Immutable, owner-scoped plan/task/resource-version selection."""

    __tablename__ = "learning_contexts"
    __table_args__ = (UniqueConstraint("user_id", "client_request_id", name="uq_learning_context_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("learning_paths.id"), nullable=False, index=True)
    module_id: Mapped[str] = mapped_column(String(120), nullable=False)
    task_key: Mapped[str] = mapped_column(String(120), nullable=False)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id"), nullable=True)
    resource_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ContextExercise(Base):
    """Generated exercise membership and evaluation evidence within one task."""

    __tablename__ = "context_exercises"
    context_id: Mapped[str] = mapped_column(ForeignKey("learning_contexts.id"), primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), primary_key=True)
    generation_task_id: Mapped[int] = mapped_column(ForeignKey("assistant_tasks.id"), nullable=False)
    feedback_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Exercise(Base):
    """Exercise generated for a knowledge point."""

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    analysis: Mapped[str] = mapped_column(Text, default="")
    assistant_operation_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)


class ExerciseKnowledgePoint(Base):
    """Explicit reviewed multi-point membership; model labels are not evidence."""

    __tablename__ = "exercise_knowledge_points"
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ExerciseFavorite(TimestampMixin, Base):
    """A learner's saved exercise with a display snapshot."""

    __tablename__ = "exercise_favorites"
    __table_args__ = (UniqueConstraint("user_id", "exercise_id", name="uq_exercise_favorite_user_exercise"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_point: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    question_type: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    analysis: Mapped[str] = mapped_column(Text, default="", nullable=False)


class StudyNote(TimestampMixin, Base):
    """Private learner-authored note, distinct from public generated resources."""

    __tablename__ = "study_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    learning_context_id: Mapped[str | None] = mapped_column(ForeignKey("learning_contexts.id"), nullable=True)
    source_resource_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_locator: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReviewCard(TimestampMixin, Base):
    """Private learner-authored flashcard with a due date."""

    __tablename__ = "review_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    front: Mapped[str] = mapped_column(String(500), nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    source_note_id: Mapped[int | None] = mapped_column(ForeignKey("study_notes.id", ondelete="SET NULL"), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5, nullable=False)
    repetitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CardReviewEvent(Base):
    """One recorded flashcard review; kept separate from the card's current schedule."""

    __tablename__ = "card_review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("review_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    next_due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class AnswerRecord(Base):
    """A learner's answer submission."""

    __tablename__ = "answer_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_spent: Mapped[int] = mapped_column(Integer, default=0)
    evaluation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    user: Mapped[User] = relationship(back_populates="answer_records")


class LearningReport(TimestampMixin, Base):
    """Generated learning report."""

    __tablename__ = "learning_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="reports")


class TranscriptImport(TimestampMixin, Base):
    """Uploaded transcript and its normalized preview data."""

    __tablename__ = "transcript_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parse_status: Mapped[str] = mapped_column(String(20), default="parsed", nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    field_mapping_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    normalized_rows_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class TranscriptScore(TimestampMixin, Base):
    """One normalized score row extracted from a transcript."""

    __tablename__ = "transcript_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("transcript_imports.id", ondelete="CASCADE"), nullable=False, index=True)
    student_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    student_no: Mapped[str] = mapped_column(String(80), default="", nullable=False, index=True)
    student_name: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    class_name: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(100), default="", nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    exam_date: Mapped[str | None] = mapped_column(String(30), nullable=True)
    chapter: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    question_scores_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence_json: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class TranscriptAnalysis(TimestampMixin, Base):
    """Persisted multi-agent transcript analysis and report."""

    __tablename__ = "transcript_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("transcript_imports.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), default="student", nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    share_token: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    report_text: Mapped[str] = mapped_column(Text, default="")
    data_quality: Mapped[str] = mapped_column(String(20), default="sufficient", nullable=False)


class Course(TimestampMixin, Base):
    """A teacher-owned course that can contain one or more classes."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    teacher_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class Classroom(TimestampMixin, Base):
    """Persistent teaching class with an optional backing course."""

    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    teacher_name: Mapped[str] = mapped_column(String(100), nullable=False)
    teacher_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    invite_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", nullable=False)
    # "invite" keeps the historical invitation-code flow; "open" lets students
    # self-enroll from the classroom plaza without a code.
    join_mode: Mapped[str] = mapped_column(
        String(16), default="invite", server_default="invite", nullable=False
    )
    description: Mapped[str] = mapped_column(
        Text, default="", server_default="", nullable=False
    )
    objective: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    syllabus: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    semester: Mapped[str] = mapped_column(
        String(40), default="", server_default="", nullable=False
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    capacity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class ClassEnrollment(TimestampMixin, Base):
    """Student membership in one class."""

    __tablename__ = "class_enrollments"
    __table_args__ = (UniqueConstraint("class_id", "student_user_id", name="uq_class_student"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True)
    student_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class Assignment(TimestampMixin, Base):
    """Homework published by a teacher to a class."""

    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    teacher_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="published", nullable=False, index=True)


class AssignmentSubmission(TimestampMixin, Base):
    """One student's persisted assignment submission and teacher review."""

    __tablename__ = "assignment_submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_user_id", name="uq_assignment_student"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted", nullable=False, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    teacher_comment: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SubmissionRevision(TimestampMixin, Base):
    """Append-only snapshots of submission and grading changes."""

    __tablename__ = "submission_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("assignment_submissions.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class HomeworkAttachment(TimestampMixin, Base):
    """Private original files bound to one assignment and their submitting student."""

    __tablename__ = "homework_attachments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    student_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    submission_id: Mapped[int | None] = mapped_column(ForeignKey("assignment_submissions.id", ondelete="CASCADE"), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    content_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DiscussionThread(TimestampMixin, Base):
    """Course/class discussion topic."""

    __tablename__ = "discussion_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=True, index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DiscussionReply(TimestampMixin, Base):
    """Reply in a discussion thread."""

    __tablename__ = "discussion_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("discussion_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class Notification(TimestampMixin, Base):
    """Persistent user notification produced by learning workflows."""

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "event_key", name="uq_notification_user_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(30), default="system", nullable=False, index=True)
    related_type: Mapped[str] = mapped_column(String(30), default="")
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationDispatch(TimestampMixin, Base):
    """Idempotent, transactional publication receipt; bounded recipient fanout."""

    __tablename__ = "notification_dispatches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    request_key: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("sender_id", "request_key", name="uq_dispatch_request"),)


class SystemSubject(TimestampMixin, Base):
    """Administrator-managed subject catalog."""

    __tablename__ = "system_subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    aliases_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    outline_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    construction_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PLANNED", server_default="PLANNED")


class KnowledgeDocument(TimestampMixin, Base):
    """Metadata adapter over the existing corpus and private uploaded originals."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    corpus_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("system_subjects.id"), nullable=True, index=True)
    chapter: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    creator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_candidates.id"), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeDocumentPoint(Base):
    __tablename__ = "knowledge_document_points"

    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), primary_key=True)
    point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), primary_key=True)


class SystemConfig(Base):
    """Persistent system configuration entry."""

    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(TimestampMixin, Base):
    """Persistent administrator audit record."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)


class TeachingScope(TimestampMixin, Base):
    """Teacher-defined learning scope delivered to a class or one learner."""

    __tablename__ = "teaching_scopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    student_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    knowledge_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    learning_direction: Mapped[str] = mapped_column(String(200), nullable=False)
    courseware_title: Mapped[str] = mapped_column(String(120), nullable=False)
    courseware_content: Mapped[str] = mapped_column(Text, nullable=False)
    teaching_goal: Mapped[str] = mapped_column(String(300), default="")


class ProfileConversation(TimestampMixin, Base):
    """Conversation history captured while building a learner profile."""

    __tablename__ = "profile_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class ChatSession(TimestampMixin, Base):
    """Chat session for continuous Q&A conversations."""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(50), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    messages: Mapped[list[ChatMessage]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ChatMessage(TimestampMixin, Base):
    """Individual message within a chat session."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(50), default="")  # small_model, large_model
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class AssistantTask(TimestampMixin, Base):
    """A durable assistant operation bound to one authenticated learner."""

    __tablename__ = "assistant_tasks"
    __table_args__ = (UniqueConstraint("user_id", "client_request_id", name="uq_assistant_task_request"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    client_request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    current_step: Mapped[str] = mapped_column(String(100), nullable=False, default="等待执行")
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    execution_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KnowledgeBuildTask(TimestampMixin, Base):
    """Durable queue entry for shared knowledge-base operations."""

    __tablename__ = "knowledge_build_tasks"
    __table_args__ = (
        UniqueConstraint("actor_user_id", "client_request_id", name="uq_knowledge_build_task_request"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(40), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    requirements_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED", index=True)
    current_step: Mapped[str] = mapped_column(String(100), nullable=False, default="等待执行")
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    execution_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parent_task_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_build_tasks.id"), nullable=True)


class KnowledgeMaintenancePlan(TimestampMixin, Base):
    """Administrator-owned recurring or one-time knowledge inspection plan."""

    __tablename__ = "knowledge_maintenance_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_task_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_build_tasks.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")


class KnowledgeBudgetCounter(Base):
    """Atomic reservations shared by API and worker processes."""

    __tablename__ = "knowledge_budget_counters"
    scope_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    search_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetch_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_cost_micros: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class KnowledgeCandidate(TimestampMixin, Base):
    """Administrator-reviewed knowledge prepared from one fetched source."""

    __tablename__ = "knowledge_candidates"
    __table_args__ = (
        UniqueConstraint("source_task_id", name="uq_knowledge_candidate_source_task"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    source_task_id: Mapped[int] = mapped_column(ForeignKey("knowledge_build_tasks.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge_point: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", index=True)
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    license_name: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    license_evidence_url: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    publication_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeVersion(TimestampMixin, Base):
    """Immutable publication record for an approved knowledge candidate."""

    __tablename__ = "knowledge_versions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "content_hash", name="uq_knowledge_version_candidate_content"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("knowledge_candidates.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge_point: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    corpus_path: Mapped[str] = mapped_column(Text, nullable=False)
    published_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    license_name: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    license_evidence_url: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")


class AssistantAgentExecution(TimestampMixin, Base):
    """Observable agent stage and outcome for an assistant task."""

    __tablename__ = "assistant_agent_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("assistant_tasks.id"), nullable=False, index=True)
    agent_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AssistantMemory(TimestampMixin, Base):
    """Learner-confirmed assistant context, isolated by user and course."""

    __tablename__ = "assistant_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    course_key: Mapped[str] = mapped_column(String(100), nullable=False, default="", index=True)
    memory_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str] = mapped_column(String(100), nullable=False, default="user_confirmed")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AssistantAttachment(TimestampMixin, Base):
    """Text extracted from a learner-uploaded document for explicit QA use."""

    __tablename__ = "assistant_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
