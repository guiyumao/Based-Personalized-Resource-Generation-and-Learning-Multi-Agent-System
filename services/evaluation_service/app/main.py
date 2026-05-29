"""FastAPI entrypoint for the evaluation service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    allow_origins=[
        "http://127.0.0.1:5175",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(reports.router, prefix="/evaluation", tags=["evaluation"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """Evaluation service health endpoint."""

    return {"status": "ok", "service": "evaluation-service"}
