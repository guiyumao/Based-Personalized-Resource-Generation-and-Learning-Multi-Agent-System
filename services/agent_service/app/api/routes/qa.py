"""Routes for intelligent tutoring Q&A and learning analysis."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.agent import CoordinationRequest, QARequest, QAResponse
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.agent_service.app.services.qa_service import QAService

router = APIRouter()


@router.post("/analyze", response_model=QAResponse)
def analyze_question(
    payload: QARequest,
    db: Session = Depends(get_db),
) -> QAResponse:
    """Answer one student question through profile + graph + QA agents."""

    intent = QAService.detect_intent_mode_from_request(payload)
    knowledge_point = QAService.infer_route_knowledge_point_from_request(payload)
    force_agents = ["qa_agent"] if intent["mode"] == "general" else [
        "learner_profiling_agent",
        "knowledge_graph_agent",
        "qa_agent",
    ]
    result = CoordinatorWorkflow(db).run(
        CoordinationRequest(
            user_id=int(payload.student_id) if payload.student_id.isdigit() else 0,
            intent=f"{intent['mode']} qa question analysis",
            knowledge_point=knowledge_point,
            payload={
                **payload.model_dump(),
                "execute": True,
                "force_agents": force_agents,
                "intent_mode": intent["mode"],
                "intent_reason": intent["reason"],
            },
        )
    )
    output = result.get("outputs", {}).get("qa_agent", {})
    if output.get("status") == "failed":
        raise HTTPException(status_code=404, detail=str(output.get("error") or "QA agent failed"))
    qa = output.get("qa")
    if not isinstance(qa, dict):
        raise HTTPException(status_code=503, detail="QA agent did not return an answer")
    return QAResponse(**qa)
