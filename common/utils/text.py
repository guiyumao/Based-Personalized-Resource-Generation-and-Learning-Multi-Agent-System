"""Text helpers for placeholder and unreadable content detection."""

from __future__ import annotations

import unicodedata

PLACEHOLDER_SESSION_TITLES: frozenset[str] = frozenset()


def normalize_session_title_key(title: str | None) -> str:
    """Normalize a session title for placeholder matching."""

    return (title or "").strip().lower()


def is_placeholder_session_title(title: str | None) -> bool:
    """Return whether the title is a known generic placeholder."""

    return normalize_session_title_key(title) in PLACEHOLDER_SESSION_TITLES


def looks_like_unreadable_text(value: str | None) -> bool:
    """Detect obviously unreadable text produced by broken encoding or placeholders."""

    normalized = (value or "").strip()
    if not normalized:
        return True
    if "\ufffd" in normalized:
        return True
    if _contains_private_use_char(normalized):
        return True
    if not any(_is_meaningful_char(ch) for ch in normalized):
        return True

    question_mark_count = normalized.count("?") + normalized.count("？")
    if question_mark_count >= 2 and question_mark_count >= max(2, len(normalized) // 2):
        return True

    return False


def _contains_private_use_char(value: str) -> bool:
    return any(unicodedata.category(ch) == "Co" for ch in value)


def _is_meaningful_char(ch: str) -> bool:
    category = unicodedata.category(ch)
    return category[0] in {"L", "N"}
