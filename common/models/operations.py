"""Operational metadata only: no model prompts, answers, keys or endpoints."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base import Base


class ModelCall(Base):
    __tablename__ = "model_calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(160))
    response_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    mode: Mapped[str] = mapped_column(String(12), index=True)
    feature: Mapped[str] = mapped_column(String(160), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    task_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    usage_status: Mapped[str] = mapped_column(String(20))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class WorkerInstance(Base):
    __tablename__ = "worker_instances"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    pid: Mapped[int] = mapped_column(Integer)
    capabilities: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_interval: Mapped[int] = mapped_column(Integer)
    batches: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class TaskAttempt(Base):
    __tablename__ = "task_attempts"
    task_kind: Mapped[str] = mapped_column(String(24), primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
