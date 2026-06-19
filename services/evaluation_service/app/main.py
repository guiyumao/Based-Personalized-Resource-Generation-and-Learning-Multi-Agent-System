"""FastAPI entrypoint for the evaluation service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.cors import get_cors_allow_origins
from common.logging.setup import configure_logging
from services.evaluation_service.app.api.routes import reports

configure_logging("evaluation-service")

app = FastAPI(
    title="evaluation-service",
    version="0.2.0",
    description="Evaluation and reporting service for learner progress.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(reports.router, prefix="/evaluation", tags=["evaluation"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """Evaluation service health endpoint."""

    return {"status": "ok", "service": "evaluation-service"}
