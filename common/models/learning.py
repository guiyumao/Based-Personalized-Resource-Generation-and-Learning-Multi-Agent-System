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


class LearningPath(TimestampMixin, Base):
    """Personalized learning path."""

    __tablename__ = "learning_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    path_data_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")

    user: Mapped[User] = relationship(back_populates="learning_paths")
    tasks: Mapped[list[LearningTask]] = relationship(back_populates="path")


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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(30), default="system", nullable=False, index=True)
    related_type: Mapped[str] = mapped_column(String(30), default="")
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class SystemSubject(TimestampMixin, Base):
    """Administrator-managed subject catalog."""

    __tablename__ = "system_subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


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
