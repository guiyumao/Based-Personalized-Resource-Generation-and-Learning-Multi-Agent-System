"""Routes for intelligent tutoring Q&A and learning analysis."""

from fastapi import APIRouter

from common.schemas.agent import QARequest, QAResponse
from services.agent_service.app.services.qa_service import QAService

router = APIRouter()


@router.post("/analyze", response_model=QAResponse)
def analyze_question(payload: QARequest) -> QAResponse:
    """Answer one student question and return structured learning analysis."""

    service = QAService()
    return QAResponse(**service.analyze_question(payload))
