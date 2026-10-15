"""Knowledge graph routes.

Performance note (DEF-012): every route here must stay off the LLM request path.
``sync_courseware_to_graph(..., allow_llm=False)`` extracts relations from SQL,
Neo4j and stored courseware content only; the LLM enrichment runs in a background
worker and is merged into the cache, so a graph request returns in milliseconds.
"""

from fastapi import APIRouter, Depends, HTTPException

from common.dependencies import get_current_user
from common.models.learning import User
from common.schemas.agent import GraphQueryRequest, GraphVisualizationResponse
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository

router = APIRouter()


@router.get("/cache-stats")
def get_cache_stats(_user: User = Depends(get_current_user)) -> dict[str, object]:
    """Expose knowledge-graph cache counters for SLO reporting.

    Read-only, aggregate, non-identifying counters: they contain no knowledge
    point, user or tenant data, so any authenticated caller may read them. This
    lets ``tests/global/probe_perf.py`` record a real cache-hit rate instead of
    inferring one from latency alone.
    """

    stats = KnowledgeGraphRepository.visualization_cache_stats()
    total_lookups = stats.hits + stats.misses
    return {
        "hits": stats.hits,
        "misses": stats.misses,
        "sets": stats.sets,
        "evictions": stats.evictions,
        "expirations": stats.expirations,
        "entries": stats.entries,
        "hit_rate": round(stats.hits / total_lookups, 4) if total_lookups else None,
    }


@router.post("/dependencies")
def get_dependency_path(payload: GraphQueryRequest) -> dict[str, object]:
    """Return dependency chains for one knowledge point."""

    repository = KnowledgeGraphRepository.acquire_shared()
    try:
        # Sync courseware content into graph relations before querying
        repository.sync_courseware_to_graph(payload.knowledge_point)
        return {
            "knowledge_point": payload.knowledge_point,
            "dependencies": repository.find_dependency_path(
                payload.knowledge_point, payload.max_depth
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        KnowledgeGraphRepository.release_shared()


@router.get("/related-resources/{knowledge_point}")
def get_related_resources(knowledge_point: str) -> dict[str, object]:
    """Return resources associated with a knowledge point."""

    repository = KnowledgeGraphRepository.acquire_shared()
    try:
        repository.sync_courseware_to_graph(knowledge_point)
        return {
            "knowledge_point": knowledge_point,
            "resources": repository.find_related_resources(knowledge_point),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        KnowledgeGraphRepository.release_shared()


@router.post("/visualization", response_model=GraphVisualizationResponse)
def get_visualization_graph(payload: GraphQueryRequest) -> GraphVisualizationResponse:
    """Return visualization-ready node and edge data."""

    repository = KnowledgeGraphRepository.acquire_shared()
    try:
        repository.sync_courseware_to_graph(payload.knowledge_point, allow_llm=False)
        result = repository.get_visualization_graph(payload.knowledge_point, payload.max_depth)
        return GraphVisualizationResponse(
            knowledge_point=payload.knowledge_point,
            nodes=result.get("nodes", []),
            edges=result.get("edges", []),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        KnowledgeGraphRepository.release_shared()
