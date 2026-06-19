"""Shared CORS configuration helpers."""

from __future__ import annotations

from common.config import get_settings


def get_cors_allow_origins() -> list[str]:
    """Return configured CORS origins for FastAPI services."""

    return list(get_settings().cors_allow_origins)
