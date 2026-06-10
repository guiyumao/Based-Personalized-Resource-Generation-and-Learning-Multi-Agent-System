"""Routes for continuous chat conversations with large-small model collaboration."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.agent import (
    ChatMessageInput,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionSummary,
)
from services.agent_service.app.services.chat_service import ChatService

router = APIRouter()


@router.post("/sessions/new", response_model=ChatSessionDetail)
def create_chat_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
) -> ChatSessionDetail:
    """Create a new chat session."""
    service = ChatService(db)
    return service.create_session(payload)


@router.get("/sessions", response_model=list[ChatSessionSummary])
def list_chat_sessions(
    user_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[ChatSessionSummary]:
    """List all chat sessions for a user."""
    service = ChatService(db)
    return service.list_sessions(user_id, limit)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_chat_session(
    session_id: int,
    user_id: int,
    db: Session = Depends(get_db),
) -> ChatSessionDetail:
    """Get a chat session with message history."""
    service = ChatService(db)
    session = service.get_session(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.post("/chat", response_model=ChatResponse)
def send_chat_message(
    payload: ChatMessageInput,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Send a message in a chat session and get AI response."""
    service = ChatService(db)
    try:
        return service.send_message(payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process message: {str(e)}")


@router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: int,
    user_id: int,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete a chat session and all its messages."""
    service = ChatService(db)
    success = service.delete_session(session_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"status": "deleted", "session_id": str(session_id)}
