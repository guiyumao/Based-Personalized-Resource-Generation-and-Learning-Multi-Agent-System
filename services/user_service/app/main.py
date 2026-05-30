"""FastAPI entrypoint for the user service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.db.bootstrap import ensure_database_schema, ensure_default_admin
from common.db.session import SessionLocal
from common.logging.setup import configure_logging
from services.user_service.app.api.routes import users

configure_logging("user-service")

app = FastAPI(
    title="user-service",
    version="0.1.0",
    description="User management service for the personalized learning platform.",
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
app.include_router(users.router, prefix="/users", tags=["users"])


@app.on_event("startup")
def startup_bootstrap() -> None:
    """Ensure local development auth can work without manual DB setup."""

    ensure_database_schema()
    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()


@app.get("/health", summary="Health check")
def health_check() -> dict[str, str]:
    """Simple liveness probe."""

    return {"status": "ok", "service": "user-service"}
