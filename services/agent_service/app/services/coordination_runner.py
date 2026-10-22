"""Shared execution body for the coordinator workflow.

Both the synchronous route and the async RabbitMQ worker call this function so
the two paths cannot drift apart.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from common.config import get_settings
from common.performance import set_trace_context
from common.schemas.agent import CoordinationRequest, CoordinationResponse
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow


def run_coordination(payload: CoordinationRequest, db: Session) -> CoordinationResponse:
    """Execute one coordinated agent request and return the response payload."""

    settings = get_settings()
    requested_agents = set(payload.payload.get("force_agents") or [])
    if payload.payload.get("include_exercises"):
        requested_agents.add("exercise_generation_agent")

    agent_deadlines = {
        "qa_agent": settings.qa_deadline_seconds,
        "path_planning_agent": settings.learning_path_deadline_seconds,
        "resource_generation_agent": settings.courseware_deadline_seconds,
        "exercise_generation_agent": settings.exercise_deadline_seconds,
        "evaluation_feedback_agent": settings.report_deadline_seconds,
    }
    selected_deadlines = [agent_deadlines[name] for name in requested_agents if name in agent_deadlines]
    intent = payload.intent.lower()
    if not selected_deadlines:
        if "learning path" in intent or "学习路径" in intent or "路径规划" in intent:
            selected_deadlines.append(settings.learning_path_deadline_seconds)
        if "qa" in intent or "答疑" in intent or "问题" in intent:
            selected_deadlines.append(settings.qa_deadline_seconds)
        if "courseware" in intent or "课件" in intent or "资源" in intent:
            selected_deadlines.append(settings.courseware_deadline_seconds)
        if "exercise" in intent or "练习" in intent:
            selected_deadlines.append(settings.exercise_deadline_seconds)
        if "report" in intent or "报告" in intent or "评估" in intent:
            selected_deadlines.append(settings.report_deadline_seconds)

    coordinator_deadline = sum(selected_deadlines) if selected_deadlines else None
    set_trace_context(
        user_id=payload.user_id,
        task_type="agent_coordination",
        deadline_seconds=coordinator_deadline,
        retry_budget=settings.max_total_retries,
    )

    workflow = CoordinatorWorkflow(db)
    result = workflow.run(payload)
    return CoordinationResponse(**result)
