"""Core SQLAlchemy models for the learning system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, text
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

    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False)
    learning_paths: Mapped[list["LearningPath"]] = relationship(back_populates="user")
    answer_records: Mapped[list["AnswerRecord"]] = relationship(back_populates="user")
    reports: Mapped[list["LearningReport"]] = relationship(back_populates="user")


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


class LearningPath(TimestampMixin, Base):
    """Personalized learning path."""

    __tablename__ = "learning_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    path_data_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")

    user: Mapped[User] = relationship(back_populates="learning_paths")
    tasks: Mapped[list["LearningTask"]] = relationship(back_populates="path")


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

    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")


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
