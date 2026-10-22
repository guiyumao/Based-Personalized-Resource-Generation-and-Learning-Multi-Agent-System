"""FastAPI entrypoint for the teacher service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.cors import get_cors_allow_origins
from common.db.bootstrap import ensure_database_schema
from common.logging.setup import configure_logging
from services.teacher_service.app.api.routes import (
    checkin,
    classes,
    community,
    course_support,
    homework_files,
    notifications,
    plaza,
    schedule,
)

configure_logging("teacher-service")

app = FastAPI(
    title="teacher-service",
    version="0.2.0",
    description="Teacher-facing class management and homework service.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(notifications.router, prefix="/learning/notifications", tags=["notifications"])
app.include_router(checkin.router, prefix="/learning/checkin", tags=["checkin"])
app.include_router(plaza.router, prefix="/learning", tags=["classroom-plaza"])
app.include_router(schedule.router, prefix="/learning", tags=["classroom-schedule"])
app.include_router(classes.router, prefix="/teacher", tags=["teacher"])
app.include_router(course_support.router, prefix="/teacher", tags=["course-support"])
app.include_router(homework_files.router, prefix="/teacher", tags=["homework-files"])
app.include_router(community.router, prefix="/learning", tags=["learning-community"])


@app.on_event("startup")
def startup_bootstrap() -> None:
    """Ensure local persistence tables exist when the teacher service runs alone."""

    ensure_database_schema()


@app.get("/health")
def health_check() -> dict[str, str]:
    """Teacher service health endpoint."""

    return {"status": "ok", "service": "teacher-service"}
