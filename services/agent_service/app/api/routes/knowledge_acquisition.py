from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import User
from services.agent_service.app.services.knowledge_acquisition import acquire_context

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-acquisition"])


class KnowledgeContextRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    knowledge_point: str = Field(min_length=1, max_length=100)
    allow_web: bool = False


@router.post("/context")
def context(payload: KnowledgeContextRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return acquire_context(db, actor_user_id=user.id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
