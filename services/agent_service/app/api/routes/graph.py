"""Knowledge graph routes.

Read routes use authenticated, deterministic sources and never schedule models
or write shared relations. Administrators may explicitly queue reviewed
construction through the existing budgeted, cancellable knowledge worker.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user, require_role
from common.models.learning import KnowledgePoint, SystemSubject, User
from common.schemas.agent import GraphQueryRequest, GraphVisualizationResponse
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.agent_service.app.services.graph_access import private_resource_graph
from services.agent_service.app.services.knowledge_tasks import (
    KnowledgeTaskConflict,
    create_task,
    serialize_task,
)

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
def get_dependency_path(payload: GraphQueryRequest, _user: User = Depends(get_current_user)) -> dict[str, object]:
    """Return dependency chains for one knowledge point."""

    repository = KnowledgeGraphRepository.acquire_shared()
    try:
        if payload.resource_id is not None:
            raise HTTPException(422, "Dependencies use the public knowledge graph")
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
def get_related_resources(knowledge_point: str, _user: User = Depends(get_current_user)) -> dict[str, object]:
    """Return resources associated with a knowledge point."""

    repository = KnowledgeGraphRepository.acquire_shared()
    try:
        return {
            "knowledge_point": knowledge_point,
            "resources": repository.find_related_resources(knowledge_point),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        KnowledgeGraphRepository.release_shared()


@router.post("/visualization", response_model=GraphVisualizationResponse)
def get_visualization_graph(payload: GraphQueryRequest, _user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)) -> GraphVisualizationResponse:
    """Return visualization-ready node and edge data."""

    if payload.resource_id is not None:
        graph = private_resource_graph(db, _user, payload.resource_id, payload.knowledge_point, payload.resource_version)
        return GraphVisualizationResponse(knowledge_point=payload.knowledge_point, **graph)
    repository = KnowledgeGraphRepository.acquire_shared()
    try:
        result = repository.get_visualization_graph(payload.knowledge_point, payload.max_depth, allow_enrichment=False)
        return GraphVisualizationResponse(
            knowledge_point=payload.knowledge_point,
            nodes=result.get("nodes", []),
            edges=result.get("edges", []),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        KnowledgeGraphRepository.release_shared()


class GraphEnrichmentRequest(BaseModel):
    point_id: int = Field(gt=0)
    client_request_id: str = Field(min_length=8, max_length=80)


@router.post("/enrichment", status_code=202)
def propose_graph_enrichment(payload: GraphEnrichmentRequest, db: Session = Depends(get_db),
                             user: User = Depends(require_role("admin"))) -> dict:
    """Budgeted construction produces a candidate for review, not public edges."""
    point = db.get(KnowledgePoint, payload.point_id)
    subject = db.get(SystemSubject, point.subject_id) if point else None
    if not point or not subject or not subject.code:
        raise HTTPException(404, "Confirmed subject and knowledge point required")
    try:
        task = create_task(db, actor_user_id=user.id, client_request_id=payload.client_request_id,
                           operation_type="BUILD_POINT", subject=subject.code,
                           requirements={"point_id": point.id, "mode": "COMPLETE_POINT", "focus": "完善先修关系和学习关联，须审核后发布"})
    except KnowledgeTaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return serialize_task(task)
