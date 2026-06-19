"""FastAPI entrypoint for the system service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.cors import get_cors_allow_origins
from common.logging.setup import configure_logging
from services.system_service.app.api.routes import admin

configure_logging("system-service")

app = FastAPI(
    title="system-service",
    version="0.2.0",
    description="System administration service for roles, subjects, config and logs.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(admin.router, prefix="/system", tags=["system"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """System service health endpoint."""

    return {"status": "ok", "service": "system-service"}
