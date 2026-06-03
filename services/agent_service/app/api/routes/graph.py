"""Knowledge graph routes."""

from fastapi import APIRouter

from common.schemas.agent import GraphQueryRequest, GraphVisualizationResponse
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository

router = APIRouter()


@router.post("/dependencies")
def get_dependency_path(payload: GraphQueryRequest) -> dict[str, object]:
    """Return dependency chains for a knowledge point."""

    repository = KnowledgeGraphRepository()
    try:
        return {
            "knowledge_point": payload.knowledge_point,
            "dependencies": repository.find_dependency_path(payload.knowledge_point, payload.max_depth),
        }
    finally:
        repository.close()


@router.get("/related-resources/{knowledge_point}")
def get_related_resources(knowledge_point: str) -> dict[str, object]:
    """Return resources associated with a knowledge point."""

    repository = KnowledgeGraphRepository()
    try:
        return {
            "knowledge_point": knowledge_point,
            "resources": repository.find_related_resources(knowledge_point),
        }
    finally:
        repository.close()


@router.post("/visualization", response_model=GraphVisualizationResponse)
def get_visualization_graph(payload: GraphQueryRequest) -> GraphVisualizationResponse:
    """Return visualization-ready node and edge data."""

    repository = KnowledgeGraphRepository()
    try:
        result = repository.get_visualization_graph(payload.knowledge_point, payload.max_depth)
        return GraphVisualizationResponse(
            knowledge_point=payload.knowledge_point,
            nodes=result["nodes"],
            edges=result["edges"],
        )
    finally:
        repository.close()
