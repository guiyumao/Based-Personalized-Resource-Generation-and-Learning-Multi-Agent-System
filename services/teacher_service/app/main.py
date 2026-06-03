"""FastAPI entrypoint for the teacher service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.logging.setup import configure_logging
from services.teacher_service.app.api.routes import classes

configure_logging("teacher-service")

app = FastAPI(
    title="teacher-service",
    version="0.2.0",
    description="Teacher-facing class management and homework service.",
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
app.include_router(classes.router, prefix="/teacher", tags=["teacher"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """Teacher service health endpoint."""

    return {"status": "ok", "service": "teacher-service"}
