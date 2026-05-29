"""Routes for resource generation agent."""

from fastapi import APIRouter

from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.resource_generation import ResourceGenerationService

router = APIRouter()


@router.post("/generate")
def generate_resource(payload: ResourceGenerationRequest) -> dict[str, object]:
    """Generate a personalized resource with RAG context."""

    service = ResourceGenerationService()
    return service.generate_courseware(payload)
