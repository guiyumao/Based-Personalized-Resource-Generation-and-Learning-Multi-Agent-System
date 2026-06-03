"""Shared API response models."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified response envelope for service APIs."""

    code: int = Field(default=200, description="Application-level status code.")
    data: T
    message: str = Field(default="", description="Human-readable status message.")
