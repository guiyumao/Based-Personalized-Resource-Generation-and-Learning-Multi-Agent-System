"""Stable business errors for AI initialization and inference failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AIServiceError(RuntimeError):
    """An AI failure that can be safely mapped to an API business error."""

    code: str
    user_message: str
    http_status: int
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        super().__init__(self.code)


class AIModelInitializationTimeoutError(AIServiceError):
    """The request deadline expired before a usable model was available."""

    def __init__(self, *, raw_message: str = "") -> None:
        super().__init__(
            code="AI_MODEL_INITIALIZATION_TIMEOUT",
            user_message="AI助教正在加载中，请稍后重试",
            http_status=503,
        )
        self.raw_message = raw_message or "AI request deadline exhausted before model initialization"


class AIInferenceTimeoutError(AIServiceError):
    """The model was available, but generation exceeded its request budget."""

    def __init__(self, *, raw_message: str = "") -> None:
        super().__init__(
            code="AI_INFERENCE_TIMEOUT",
            user_message="AI助教响应较慢，请稍后重试",
            http_status=504,
        )
        self.raw_message = raw_message or "AI inference timed out"


def is_timeout_exception(exc: BaseException) -> bool:
    """Recognize provider timeout shapes without hiding unrelated failures."""

    if isinstance(exc, TimeoutError):
        return True
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return "timeout" in name or "timed out" in message or "deadline exceeded" in message
