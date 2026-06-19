"""Helpers for bootstrapping local database state."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from common.db.base import Base
from common.db.session import engine
from common.models import learning  # noqa: F401
from common.models.learning import User, UserProfile
from common.security.auth import hash_password, verify_password


def ensure_database_schema() -> None:
    """Create all database tables when running local services directly."""

    Base.metadata.create_all(bind=engine)
    _ensure_legacy_columns()


def ensure_default_admin(db: Session) -> None:
    """Seed a local administrator account for manual testing."""

    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            role="admin",
            email="admin@example.com",
        )
        db.add(admin)
        db.flush()

        db.add(
            UserProfile(
                user_id=admin.id,
                mastery_json={},
                learning_style="",
                cognitive_abilities={},
                habits={},
            )
        )
        db.commit()
        return

    updated = False
    if admin.role != "admin":
        admin.role = "admin"
        updated = True
    if admin.email != "admin@example.com":
        admin.email = "admin@example.com"
        updated = True
    if not verify_password("admin123", admin.password_hash):
        admin.password_hash = hash_password("admin123")
        updated = True

    profile = db.get(UserProfile, admin.id)
    if profile is None:
        db.add(
            UserProfile(
                user_id=admin.id,
                mastery_json={},
                learning_style="",
                cognitive_abilities={},
                habits={},
            )
        )
        updated = True

    if updated:
        db.commit()


def _ensure_legacy_columns() -> None:
    """Backfill columns that were added after the initial local schema."""

    inspector = inspect(engine)
    if "answer_records" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("answer_records")}
    statements: list[str] = []

    if "evaluation_json" not in existing_columns:
        statements.append("ALTER TABLE answer_records ADD COLUMN evaluation_json JSON")
    if "created_at" not in existing_columns:
        statements.append("ALTER TABLE answer_records ADD COLUMN created_at DATETIME")

    # ── profile_analysis (2026-06-19) ──
    if "user_profiles" in inspector.get_table_names():
        profile_columns = {col["name"] for col in inspector.get_columns("user_profiles")}
        if "profile_analysis" not in profile_columns:
            statements.append("ALTER TABLE user_profiles ADD COLUMN profile_analysis JSON")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
