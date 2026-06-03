"""Schemas for resource management APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResourceItem(BaseModel):
    """A managed learning resource item."""

    id: int
    title: str
    type: Literal["courseware", "exercise", "notes", "exam"]
    format: Literal["markdown", "pdf", "word"]
    status: Literal["draft", "ready", "archived"]
    knowledge_point: str
    owner_user_id: int | None = None


class ResourceStatusUpdate(BaseModel):
    """Payload for updating resource status."""

    status: Literal["draft", "ready", "archived"]


class ResourceExportRequest(BaseModel):
    """Payload for requesting a resource export."""

    export_format: Literal["pdf", "word"] = Field(description="Target export format.")
