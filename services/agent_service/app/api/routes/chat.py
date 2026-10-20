"""Routes for continuous chat conversations with large-small model collaboration."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from common.ai_errors import AIServiceError
from common.config import get_settings
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import User
from common.performance import set_trace_context
from common.schemas.agent import (
    ChatMessageInput,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionSummary,
)
from services.agent_service.app.services.chat_service import ChatService

router = APIRouter()
LOGGER = logging.getLogger(__name__)


def _assert_user_scope(requested_user_id: int, current_user: User) -> None:
    """Prevent request parameters from overriding the authenticated user."""

    if requested_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User scope does not match the authenticated account",
        )


@router.post("/sessions/new", response_model=ChatSessionDetail)
def create_chat_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionDetail:
    """Create a new chat session."""
    _assert_user_scope(payload.user_id, current_user)
    service = ChatService(db)
    return service.create_session(payload)


@router.get("/sessions", response_model=list[ChatSessionSummary])
def list_chat_sessions(
    user_id: int,
    limit: int = 50,
    keyword: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSessionSummary]:
    """List all chat sessions for a user."""
    _assert_user_scope(user_id, current_user)
    service = ChatService(db)
    return service.list_sessions(user_id, limit, keyword)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_chat_session(
    session_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionDetail:
    """Get a chat session with message history."""
    _assert_user_scope(user_id, current_user)
    service = ChatService(db)
    session = service.get_session(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.post("/chat", response_model=ChatResponse)
def send_chat_message(
    payload: ChatMessageInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Send a message in a chat session and get AI response."""
    _assert_user_scope(payload.user_id, current_user)
    settings = get_settings()
    set_trace_context(
        user_id=payload.user_id,
        task_type="chat_qa",
        deadline_seconds=settings.chat_deadline_seconds,
        retry_budget=settings.max_total_retries,
    )
    service = ChatService(db)
    try:
        return service.send_message(payload)
    except AIServiceError as exc:
        LOGGER.warning(
            "chat_ai_failure code=%s raw_error=%s",
            exc.code,
            getattr(exc, "raw_message", str(exc))[:500],
        )
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.user_message},
            headers=headers,
        ) from exc
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat storage is temporarily busy; please retry",
            headers={"Retry-After": "1"},
        ) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process message: {str(e)}") from e


@router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a chat session and all its messages."""
    _assert_user_scope(user_id, current_user)
    service = ChatService(db)
    try:
        success = service.delete_session(session_id, user_id)
    except OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat storage is temporarily busy; please retry",
            headers={"Retry-After": "1"},
        ) from exc
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"status": "deleted", "session_id": str(session_id)}
