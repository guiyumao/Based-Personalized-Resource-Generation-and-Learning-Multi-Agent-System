"""Routes for learning-path and structured exercise capabilities."""

from fastapi import APIRouter

from common.schemas.agent import (
    ExerciseGenerationRequest,
    ExerciseGenerationResponse,
    LearningPathRequest,
    LearningPathResponse,
)
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.learning_path import LearningPathService

router = APIRouter()


@router.post("/paths/generate", response_model=LearningPathResponse)
def generate_learning_path(payload: LearningPathRequest) -> LearningPathResponse:
    """Generate a lightweight personalized learning path."""

    service = LearningPathService()
    return LearningPathResponse(**service.generate_path(payload))


@router.post("/exercises/generate", response_model=ExerciseGenerationResponse)
def generate_exercises(payload: ExerciseGenerationRequest) -> ExerciseGenerationResponse:
    """Generate a structured exercise set for learner practice."""

    service = ExerciseGenerationService()
    return ExerciseGenerationResponse(**service.generate_exercises(payload))
