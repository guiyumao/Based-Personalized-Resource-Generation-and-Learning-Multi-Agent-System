"""Immutable learning artifacts and resource edit history."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base import Base


class ResourceArtifact(Base):
    __tablename__ = "resource_artifacts"
    __table_args__ = (UniqueConstraint("context_id", "kind", name="uq_context_artifact_kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"))
    context_id: Mapped[str] = mapped_column(ForeignKey("learning_contexts.id"))
    resource_version: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    relative_path: Mapped[str] = mapped_column(String(240))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResourceRevision(Base):
    __tablename__ = "resource_revisions"
    __table_args__ = (UniqueConstraint("resource_id", "version", name="uq_resource_revision_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    version: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    structured_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
