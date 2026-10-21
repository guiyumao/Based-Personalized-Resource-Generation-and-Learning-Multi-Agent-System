"""Append-only private note revisions and attributable flashcard evidence."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base import Base


class NoteRevision(Base):
    __tablename__ = "note_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("study_notes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CardKnowledgeBinding(Base):
    __tablename__ = "card_knowledge_bindings"
    card_id: Mapped[int] = mapped_column(ForeignKey("review_cards.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"))
    context_id: Mapped[str | None] = mapped_column(ForeignKey("learning_contexts.id"), nullable=True)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id"), nullable=True)
    resource_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CardReviewReceipt(Base):
    __tablename__ = "card_review_receipts"
    request_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("review_cards.id", ondelete="CASCADE"))
    event_id: Mapped[int] = mapped_column(ForeignKey("card_review_events.id", ondelete="CASCADE"))
    grade: Mapped[int] = mapped_column(Integer)
