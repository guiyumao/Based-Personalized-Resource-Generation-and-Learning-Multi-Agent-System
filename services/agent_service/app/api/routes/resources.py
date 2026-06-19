"""Routes for resource generation agent."""

from fastapi import APIRouter, HTTPException

from common.schemas.agent import ResourceGenerationRequest, ResourceGenerationResponse
from services.agent_service.app.services.resource_generation import (
    ResourceGenerationError,
    ResourceGenerationService,
)

router = APIRouter()


@router.post("/generate")
def generate_resource(payload: ResourceGenerationRequest) -> ResourceGenerationResponse:
    """Generate a personalized resource with RAG context."""

    service = ResourceGenerationService()
    try:
        return ResourceGenerationResponse(**service.generate_courseware_with_plan(payload))
    except ResourceGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
