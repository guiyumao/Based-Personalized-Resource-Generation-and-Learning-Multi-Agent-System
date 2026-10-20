"""Routes for intelligent tutoring Q&A and learning analysis."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import get_db
from common.dependencies import get_current_user, require_self_or_admin
from common.models.learning import User
from common.performance import set_trace_context
from common.schemas.agent import CoordinationRequest, QARequest, QAResponse
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.agent_service.app.services.qa_service import QAService

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/analyze", response_model=QAResponse)
def analyze_question(
    payload: QARequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QAResponse:
    """Answer one student question through profile + QA agents."""
    if not payload.student_id.isdigit():
        raise HTTPException(status_code=400, detail="Invalid student id")
    require_self_or_admin(int(payload.student_id), current_user)

    intent = QAService.detect_intent_mode_from_request(payload)
    settings = get_settings()
    set_trace_context(
        user_id=payload.student_id,
        task_type=f"qa_{intent['mode']}",
        deadline_seconds=settings.qa_deadline_seconds,
        retry_budget=settings.max_total_retries,
    )
    knowledge_point = QAService.infer_route_knowledge_point_from_request(payload)
    # The QA service performs its own knowledge-base retrieval. The graph
    # agent's result is not consumed by the answer path, so running it
    # synchronously here only consumes the same request deadline.
    force_agents = ["qa_agent"] if intent["mode"] == "general" else [
        "learner_profiling_agent",
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
        error_code = str(output.get("error_code") or "")
        if error_code in {"AI_MODEL_INITIALIZATION_TIMEOUT", "AI_INFERENCE_TIMEOUT"}:
            status_code = 503 if error_code == "AI_MODEL_INITIALIZATION_TIMEOUT" else 504
            message = (
                "AI助教正在加载中，请稍后重试"
                if status_code == 503
                else "AI助教响应较慢，请稍后重试"
            )
            LOGGER.warning(
                "qa_request_ai_timeout code=%s raw_error=%s",
                error_code,
                str(output.get("error") or "")[:500],
            )
            raise HTTPException(
                status_code=status_code,
                detail={"code": error_code, "message": message},
            )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "AI_SERVICE_UNAVAILABLE",
                "message": "AI助教暂时无法生成回答，请稍后重试",
            },
        )
    qa = output.get("qa")
    if not isinstance(qa, dict):
        raise HTTPException(status_code=503, detail="QA agent did not return an answer")
    return QAResponse(**qa)
