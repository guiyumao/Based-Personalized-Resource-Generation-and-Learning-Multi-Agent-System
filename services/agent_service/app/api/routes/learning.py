"""Routes for learning-path and structured exercise capabilities."""

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/exercises/generate", response_model=ExerciseGenerationResponse)
def generate_exercises(payload: ExerciseGenerationRequest) -> ExerciseGenerationResponse:
    """Generate a structured exercise set for learner practice."""

    service = ExerciseGenerationService()
    return ExerciseGenerationResponse(**service.generate_exercises(payload))
