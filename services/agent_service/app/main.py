"""FastAPI entrypoint for the agent service."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.config import get_settings
from common.cors import get_cors_allow_origins
from common.db.bootstrap import ensure_database_schema
from common.logging.setup import configure_logging
from common.performance import PerformanceTraceMiddleware
from services.agent_service.app.api.routes import (
    agents,
    assistant,
    chat,
    graph,
    knowledge_acquisition,
    knowledge_candidates,
    knowledge_construction,
    knowledge_documents,
    knowledge_maintenance,
    knowledge_tasks,
    knowledge_versions,
    learning,
    learning_contexts,
    learning_gaps,
    model_usage,
    operations,
    prompt_admin,
    qa,
    resource_artifacts,
    resource_editor,
    resource_revisions,
    resources,
)
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.agent_service.app.services.assistant_tasks import (
    fail_interrupted_tasks,
    task_execution_mode,
)
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
app.include_router(knowledge_tasks.router)
app.include_router(knowledge_candidates.router)
app.include_router(knowledge_construction.router)
app.include_router(knowledge_acquisition.router)
app.include_router(knowledge_versions.router)
app.include_router(knowledge_maintenance.router)
app.include_router(knowledge_documents.router)
app.include_router(learning_contexts.router)
app.include_router(learning_gaps.router)
app.include_router(operations.router)
app.include_router(model_usage.router)
app.include_router(resource_artifacts.router)
app.include_router(resource_revisions.router)
app.include_router(prompt_admin.router)
app.include_router(resource_editor.router)
app.include_router(learning.router, tags=["learning"])
app.include_router(qa.router, prefix="/qa", tags=["qa"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(assistant.router, prefix="/assistant", tags=["assistant"])


@app.on_event("startup")
def startup_bootstrap() -> None:
    """Ensure local persistence tables exist when the agent service runs alone."""

    ensure_database_schema()
    LOGGER.info("assistant_task_execution_mode=%s", task_execution_mode())
    interrupted = fail_interrupted_tasks()
    if interrupted:
        LOGGER.warning("assistant_interrupted_tasks_marked_failed count=%s", interrupted)
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
