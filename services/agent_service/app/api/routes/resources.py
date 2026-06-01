"""Routes for resource generation agent."""

from fastapi import APIRouter

from common.schemas.agent import ResourceGenerationRequest, ResourceGenerationResponse
from services.agent_service.app.services.resource_generation import ResourceGenerationService

router = APIRouter()


@router.post("/generate")
def generate_resource(payload: ResourceGenerationRequest) -> ResourceGenerationResponse:
    """Generate a personalized resource with RAG context."""

    service = ResourceGenerationService()
    return ResourceGenerationResponse(**service.generate_courseware_with_plan(payload))
