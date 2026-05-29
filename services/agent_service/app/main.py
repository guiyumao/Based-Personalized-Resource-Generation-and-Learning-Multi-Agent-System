"""FastAPI entrypoint for the agent service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.logging.setup import configure_logging
from services.agent_service.app.api.routes import agents, graph, learning, qa, resources

configure_logging("agent-service")

app = FastAPI(
    title="agent-service",
    version="0.1.0",
    description="Multi-agent orchestration service for the personalized learning platform.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5175",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(graph.router, prefix="/graph", tags=["knowledge-graph"])
app.include_router(resources.router, prefix="/resources", tags=["resource-generation"])
app.include_router(learning.router, tags=["learning"])
app.include_router(qa.router, prefix="/qa", tags=["qa"])


@app.get("/health", summary="Health check")
def health_check() -> dict[str, str]:
    """Simple liveness probe."""

    return {"status": "ok", "service": "agent-service"}
