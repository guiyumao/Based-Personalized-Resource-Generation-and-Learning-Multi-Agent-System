"""FastAPI entrypoint for the agent service."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.config import get_settings
from common.cors import get_cors_allow_origins
from common.db.bootstrap import ensure_database_schema
from common.logging.setup import configure_logging
from common.performance import PerformanceTraceMiddleware
from services.agent_service.app.api.routes import agents, chat, graph, learning, qa, resources
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.rag import ChromaRetriever

configure_logging("agent-service")
LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="agent-service",
    version="0.1.0",
    description="Multi-agent orchestration service for the personalized learning platform.",
)
app.add_middleware(PerformanceTraceMiddleware, service_name="agent-service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(graph.router, prefix="/graph", tags=["knowledge-graph"])
app.include_router(resources.router, prefix="/resources", tags=["resource-generation"])
app.include_router(learning.router, tags=["learning"])
app.include_router(qa.router, prefix="/qa", tags=["qa"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])


@app.on_event("startup")
def startup_bootstrap() -> None:
    """Ensure local persistence tables exist when the agent service runs alone."""

    ensure_database_schema()
    # Resolve and log the exact knowledge-base mode at startup. Chroma remains
    # optional for development, and Docker may start it after the API process.
    try:
        retriever = ChromaRetriever()
        LOGGER.info(
            "knowledge_base_startup %s available=%s",
            retriever.describe(),
            retriever.is_available,
        )
    except Exception as exc:
        LOGGER.warning("knowledge_base_startup_unavailable error=%s", str(exc)[:200])
    settings = get_settings()
    if settings.llm_prewarm_enabled:
        try:
            LLMFactory(settings).prewarm()
        except Exception as exc:
            LOGGER.warning("llm_model_prewarm_unavailable error=%s", str(exc)[:200])
    # Import the knowledge-graph collaborators up front: doing it lazily inside the
    # first graph request added ~2s of import time to that request (DEF-012).
    try:
        KnowledgeGraphRepository.prewarm()
    except Exception as exc:
        LOGGER.warning("graph_prewarm_unavailable error=%s", str(exc)[:200])


@app.get("/health", summary="Health check")
def health_check() -> dict[str, str]:
    """Simple liveness probe."""

    return {"status": "ok", "service": "agent-service"}
