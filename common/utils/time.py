"""Helpers for consistent timezone-aware datetime serialization."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_utc_datetime(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime.

    Project database timestamps are mostly stored as naive UTC values. This helper
    normalizes them before we serialize back to the frontend.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_utc_isoformat(value: datetime) -> str:
    """Serialize a datetime as an ISO-8601 UTC string with timezone info."""

    return ensure_utc_datetime(value).isoformat()
