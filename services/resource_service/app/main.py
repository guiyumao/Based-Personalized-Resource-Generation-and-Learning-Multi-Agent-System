"""FastAPI entrypoint for the resource service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.logging.setup import configure_logging
from services.resource_service.app.api.routes import resources

configure_logging("resource-service")

app = FastAPI(
    title="resource-service",
    version="0.2.0",
    description="Resource management service for generated learning assets.",
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
app.include_router(resources.router, prefix="/resources", tags=["resources"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """Resource service health endpoint."""

    return {"status": "ok", "service": "resource-service"}
