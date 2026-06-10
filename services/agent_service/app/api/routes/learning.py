"""Routes for learning-path, knowledge-base, and exercise capabilities."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.agent import (
    ExerciseGenerationRequest,
    ExerciseGenerationResponse,
    LearningPathAdjustRequest,
    LearningPathRequest,
    LearningPathResponse,
)
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.learning_path import LearningPathService

router = APIRouter()


@router.post("/paths/generate", response_model=LearningPathResponse)
def generate_learning_path(payload: LearningPathRequest, db: Session = Depends(get_db)) -> LearningPathResponse:
    """Generate a lightweight personalized learning path."""

    service = LearningPathService(db)
    return LearningPathResponse(**service.generate_path(payload))


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
    """Return curated university knowledge articles for the student workspace."""

    service = KnowledgeBaseService()
    articles = service.list_articles(subject=subject)
    return {
        "subjects": service.list_subjects(),
        "items": [service.article_to_dict(article) for article in articles],
    }


@router.get("/knowledge-base/search")
def search_knowledge_base(
    q: str = Query(default="", min_length=0),
    top_k: int = Query(default=6, ge=1, le=20),
) -> dict[str, object]:
    """Search curated university knowledge articles."""

    service = KnowledgeBaseService()
    if not q.strip():
        articles = service.list_articles()[:top_k]
    else:
        articles = service.search_by_keywords(q, top_k=top_k)
    return {
        "query": q,
        "items": [service.article_to_dict(article) for article in articles],
    }


@router.get("/knowledge-base/{article_id}")
def get_knowledge_article(article_id: str) -> dict[str, object]:
    """Return one curated knowledge article by id."""

    service = KnowledgeBaseService()
    for article in service.list_articles():
        payload = service.article_to_dict(article)
        if payload["id"] == article_id:
            return payload
    raise HTTPException(status_code=404, detail="Knowledge article not found")


@router.post("/exercises/generate", response_model=ExerciseGenerationResponse)
def generate_exercises(payload: ExerciseGenerationRequest) -> ExerciseGenerationResponse:
    """Generate a structured exercise set for learner practice."""

    service = ExerciseGenerationService()
    return ExerciseGenerationResponse(**service.generate_exercises(payload))
