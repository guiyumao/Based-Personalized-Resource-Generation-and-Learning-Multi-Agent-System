"""Knowledge graph routes."""

from fastapi import APIRouter

from common.schemas.agent import CoordinationRequest, GraphQueryRequest, GraphVisualizationResponse
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow

router = APIRouter()


@router.post("/dependencies")
def get_dependency_path(payload: GraphQueryRequest) -> dict[str, object]:
    """Return dependency chains through the knowledge-graph agent."""

    output = _run_graph_agent(payload)
    return {
        "knowledge_point": payload.knowledge_point,
        "dependencies": output.get("dependencies", []),
    }


@router.get("/related-resources/{knowledge_point}")
def get_related_resources(knowledge_point: str) -> dict[str, object]:
    """Return resources associated with a knowledge point through the graph agent."""

    output = _run_graph_agent(GraphQueryRequest(knowledge_point=knowledge_point, max_depth=2))
    return {
        "knowledge_point": knowledge_point,
        "resources": output.get("related_resources", []),
    }


@router.post("/visualization", response_model=GraphVisualizationResponse)
def get_visualization_graph(payload: GraphQueryRequest) -> GraphVisualizationResponse:
    """Return visualization-ready node and edge data through the graph agent."""

    result = _run_graph_agent(payload).get("visualization", {})
    return GraphVisualizationResponse(
        knowledge_point=payload.knowledge_point,
        nodes=result.get("nodes", []),
        edges=result.get("edges", []),
    )


def _run_graph_agent(payload: GraphQueryRequest) -> dict[str, object]:
    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=0,
            intent="knowledge graph visualization dependencies related resources",
            knowledge_point=payload.knowledge_point,
            payload={
                "execute": True,
                "force_agents": ["knowledge_graph_agent"],
                "max_depth": payload.max_depth,
            },
        )
    )
    output = result.get("outputs", {}).get("knowledge_graph_agent", {})
    return output if isinstance(output, dict) else {}
