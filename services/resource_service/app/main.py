"""FastAPI entrypoint for the resource service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.cors import get_cors_allow_origins
from common.db.bootstrap import ensure_database_schema
from common.logging.setup import configure_logging
from services.resource_service.app.api.routes import resources

configure_logging("resource-service")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Ensure persistence tables exist when the resource service runs alone."""

    ensure_database_schema()
    yield


app = FastAPI(
    title="resource-service",
    version="0.2.0",
    description="Resource management service for generated learning assets.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(resources.router, prefix="/resources", tags=["resources"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """Resource service health endpoint."""

    return {"status": "ok", "service": "resource-service"}
