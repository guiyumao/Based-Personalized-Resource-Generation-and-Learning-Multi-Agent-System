"""Helpers for bootstrapping local database state."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from common.db.base import Base
from common.db.session import engine
from common.models import learning  # noqa: F401
from common.models.learning import User, UserProfile
from common.security.auth import hash_password, verify_password
from common.config import get_settings


def ensure_database_schema() -> None:
    """Create all database tables when running local services directly."""

    Base.metadata.create_all(bind=engine)
    _ensure_legacy_columns()


def ensure_default_admin(db: Session) -> None:
    """Seed a local administrator account for manual testing."""

    settings = get_settings()
    if not settings.default_admin_username or not settings.default_admin_password:
        return

    admin_email = settings.default_admin_email or f"{settings.default_admin_username}@example.com"
    admin = db.query(User).filter(User.username == settings.default_admin_username).first()
    if admin is None:
        admin = User(
            username=settings.default_admin_username,
            password_hash=hash_password(settings.default_admin_password),
            role="admin",
            email=admin_email,
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
    if admin.email != admin_email:
        admin.email = admin_email
        updated = True
    if not verify_password(settings.default_admin_password, admin.password_hash):
        admin.password_hash = hash_password(settings.default_admin_password)
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
    table_names = set(inspector.get_table_names())
    if "answer_records" not in table_names and "user_profiles" not in table_names:
        return

    statements: list[str] = []

    if "answer_records" in table_names:
        answer_record_columns = {column["name"] for column in inspector.get_columns("answer_records")}
        if "evaluation_json" not in answer_record_columns:
            statements.append("ALTER TABLE answer_records ADD COLUMN evaluation_json JSON")
        if "created_at" not in answer_record_columns:
            statements.append("ALTER TABLE answer_records ADD COLUMN created_at DATETIME")

    if "user_profiles" in table_names:
        user_profile_columns = {column["name"] for column in inspector.get_columns("user_profiles")}
        if "profile_analysis" not in user_profile_columns:
            statements.append("ALTER TABLE user_profiles ADD COLUMN profile_analysis JSON")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
