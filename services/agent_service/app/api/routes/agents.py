"""Coordinator agent routes."""

from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.agent import CoordinationRequest, CoordinationResponse
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow

router = APIRouter()


@router.post("/coordinate", response_model=CoordinationResponse)
def coordinate(payload: CoordinationRequest, db: Session = Depends(get_db)) -> CoordinationResponse:
    """Execute the coordinator LangGraph workflow."""

    workflow = CoordinatorWorkflow(db)
    result = workflow.run(payload)
    return CoordinationResponse(**result)
