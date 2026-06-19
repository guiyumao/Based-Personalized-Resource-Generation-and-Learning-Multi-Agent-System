"""Routes for resource generation agent."""

from fastapi import APIRouter, HTTPException

from common.schemas.agent import CoordinationRequest, ResourceGenerationRequest, ResourceGenerationResponse
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow

router = APIRouter()


@router.post("/generate")
def generate_resource(payload: ResourceGenerationRequest) -> ResourceGenerationResponse:
    """Generate a personalized resource through the multi-agent workflow."""

    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=payload.user_id,
            intent="courseware resource generation",
            knowledge_point=payload.knowledge_point,
            payload={
                **payload.model_dump(),
                "execute": True,
                "force_agents": ["learner_profiling_agent", "resource_generation_agent"],
            },
        )
    )
    output = result.get("outputs", {}).get("resource_generation_agent", {})
    if output.get("status") == "failed":
        raise HTTPException(status_code=503, detail=str(output.get("error") or "Resource generation failed"))
    resource = output.get("resource")
    if not isinstance(resource, dict):
        raise HTTPException(status_code=503, detail="Resource generation agent did not return a resource")
    return ResourceGenerationResponse(**resource)
