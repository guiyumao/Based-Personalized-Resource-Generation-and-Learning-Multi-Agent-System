"""Routes for intelligent tutoring Q&A and learning analysis."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.agent import CoordinationRequest, QARequest, QAResponse
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow

router = APIRouter()


@router.post("/analyze", response_model=QAResponse)
def analyze_question(
    payload: QARequest,
    db: Session = Depends(get_db),
) -> QAResponse:
    """Answer one student question through profile + graph + QA agents."""

    knowledge_point = next((item for item in payload.current_knowledge_points if item.strip()), payload.subject)
    result = CoordinatorWorkflow(db).run(
        CoordinationRequest(
            user_id=int(payload.student_id) if payload.student_id.isdigit() else 0,
            intent="qa question analysis",
            knowledge_point=knowledge_point,
            payload={
                **payload.model_dump(),
                "execute": True,
                "force_agents": ["learner_profiling_agent", "knowledge_graph_agent", "qa_agent"],
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
