"""Helpers for bootstrapping local database state."""

from __future__ import annotations

from sqlalchemy.orm import Session

from common.db.base import Base
from common.db.session import engine
from common.models import learning  # noqa: F401
from common.models.learning import User, UserProfile
from common.security.auth import hash_password, verify_password


def ensure_database_schema() -> None:
    """Create all database tables when running local services directly."""

    Base.metadata.create_all(bind=engine)


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
                learning_style="VARK",
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
                learning_style="VARK",
                cognitive_abilities={},
                habits={},
            )
        )
        updated = True

    if updated:
        db.commit()
