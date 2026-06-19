"""Routes for learning-path, knowledge-base, and exercise capabilities."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.agent import (
    CoordinationRequest,
    ExerciseGenerationRequest,
    ExerciseGenerationResponse,
    LearningPathAdjustRequest,
    LearningPathRequest,
    LearningPathResponse,
)
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.agent_service.app.services.learning_path import LearningPathService

router = APIRouter()


@router.post("/paths/generate", response_model=LearningPathResponse)
def generate_learning_path(payload: LearningPathRequest, db: Session = Depends(get_db)) -> LearningPathResponse:
    """Generate a personalized learning path through the multi-agent workflow."""

    result = CoordinatorWorkflow(db).run(
        CoordinationRequest(
            user_id=payload.user_id,
            intent="learning path plan",
            knowledge_point=payload.knowledge_point,
            payload={
                **payload.model_dump(),
                "execute": True,
                "force_agents": [
                    "learner_profiling_agent",
                    "knowledge_graph_agent",
                    "path_planning_agent",
                ],
            },
        )
    )
    output = result.get("outputs", {}).get("path_planning_agent", {})
    learning_path = output.get("learning_path")
    if not isinstance(learning_path, dict):
        raise HTTPException(status_code=503, detail="Path planning agent did not return a learning path")
    return LearningPathResponse(**learning_path)


@router.get("/paths/{user_id}", response_model=LearningPathResponse)
def get_latest_learning_path(user_id: int, db: Session = Depends(get_db)) -> LearningPathResponse:
    """Return the latest active learning path for one learner."""

    service = LearningPathService(db)
    payload = service.get_latest_path(user_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Learning path not found")
    return LearningPathResponse(**payload)


@router.post("/paths/adjust", response_model=LearningPathResponse)
def adjust_learning_path(payload: LearningPathAdjustRequest, db: Session = Depends(get_db)) -> LearningPathResponse:
    """Adjust one task state in the learner's active path."""

    service = LearningPathService(db)
    updated = service.adjust_path(payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Learning path task not found")
    return LearningPathResponse(**updated)


@router.get("/knowledge-base")
def list_knowledge_base(subject: str | None = None) -> dict[str, object]:
    """Return knowledge articles through the knowledge-base agent."""

    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=0,
            intent="knowledge base catalog",
            payload={
                "execute": True,
                "force_agents": ["knowledge_base_agent"],
                "operation": "list",
                "subject": subject,
            },
        )
    )
    output = result.get("outputs", {}).get("knowledge_base_agent", {})
    if output.get("status") == "failed":
        raise HTTPException(status_code=503, detail=str(output.get("error") or "Knowledge-base agent failed"))
    return {
        "subjects": output.get("subjects", []),
        "items": output.get("items", []),
    }


@router.get("/knowledge-base/search")
def search_knowledge_base(
    q: str = Query(default="", min_length=0),
    top_k: int = Query(default=6, ge=1, le=20),
) -> dict[str, object]:
    """Search knowledge articles through the knowledge-base agent."""

    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=0,
            intent="knowledge base search",
            payload={
                "execute": True,
                "force_agents": ["knowledge_base_agent"],
                "operation": "search",
                "query": q,
                "top_k": top_k,
            },
        )
    )
    output = result.get("outputs", {}).get("knowledge_base_agent", {})
    if output.get("status") == "failed":
        raise HTTPException(status_code=503, detail=str(output.get("error") or "Knowledge-base agent failed"))
    return {
        "query": output.get("query", q),
        "items": output.get("items", []),
    }


@router.get("/knowledge-base/{article_id}")
def get_knowledge_article(article_id: str) -> dict[str, object]:
    """Return one knowledge article through the knowledge-base agent."""

    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=0,
            intent="knowledge base article",
            payload={
                "execute": True,
                "force_agents": ["knowledge_base_agent"],
                "operation": "article",
                "article_id": article_id,
            },
        )
    )
    output = result.get("outputs", {}).get("knowledge_base_agent", {})
    if output.get("status") == "completed" and isinstance(output.get("article"), dict):
        return output["article"]
    raise HTTPException(status_code=404, detail="Knowledge article not found")


@router.post("/exercises/generate", response_model=ExerciseGenerationResponse)
def generate_exercises(payload: ExerciseGenerationRequest) -> ExerciseGenerationResponse:
    """Generate a structured exercise set through the multi-agent workflow."""

    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=payload.user_id,
            intent="exercise practice generation",
            knowledge_point=payload.knowledge_point,
            payload={
                **payload.model_dump(),
                "execute": True,
                "only_exercises": True,
                "force_agents": ["learner_profiling_agent", "exercise_generation_agent"],
            },
        )
    )
    output = result.get("outputs", {}).get("exercise_generation_agent", {})
    exercise_set = output.get("exercise_set")
    if not isinstance(exercise_set, dict):
        raise HTTPException(status_code=503, detail="Exercise generation agent did not return exercises")
    return ExerciseGenerationResponse(**exercise_set)
