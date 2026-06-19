"""Routes for intelligent tutoring Q&A and learning analysis."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.agent import QARequest, QAResponse
from services.agent_service.app.services.qa_service import QAService

router = APIRouter()


@router.post("/analyze", response_model=QAResponse)
def analyze_question(
    payload: QARequest,
    db: Session = Depends(get_db),
) -> QAResponse:
    """Answer one student question and support continuous QA sessions."""

    service = QAService(db)
    try:
        return QAResponse(**service.analyze_question(payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

