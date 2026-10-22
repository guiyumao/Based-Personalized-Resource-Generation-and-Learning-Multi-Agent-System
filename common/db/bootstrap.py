"""Helpers for bootstrapping local database state."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.base import Base
from common.db.session import engine
from common.models import checkin, learning  # noqa: F401
from common.models.learning import User, UserProfile
from common.security.auth import hash_password, verify_password


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
    index_statements: list[str] = []

    def has_operation_unique(table: str) -> bool:
        return any("assistant_operation_key" in constraint.get("column_names", [])
                   for constraint in inspector.get_unique_constraints(table)) or any(
            index.get("unique") and "assistant_operation_key" in index.get("column_names", [])
            for index in inspector.get_indexes(table)
        )

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

    if "resources" in table_names:
        resource_columns = {column["name"] for column in inspector.get_columns("resources")}
        if "title" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN title VARCHAR(200)")
        if "source_url" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN source_url TEXT")
        if "local_path" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN local_path TEXT")
        if "tags" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN tags JSON")
        if "crawl_status" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN crawl_status VARCHAR(20)")
        if "language" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN language VARCHAR(10)")
        if "summary" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN summary TEXT")
        if "generation_status" not in resource_columns:
            statements.append(
                "ALTER TABLE resources ADD COLUMN generation_status VARCHAR(20) DEFAULT 'generated'"
            )
        if "audit_status" not in resource_columns:
            statements.append(
                "ALTER TABLE resources ADD COLUMN audit_status VARCHAR(20) DEFAULT 'pending'"
            )
        if "publish_status" not in resource_columns:
            statements.append(
                "ALTER TABLE resources ADD COLUMN publish_status VARCHAR(20) DEFAULT 'draft'"
            )
        if "audit_reason" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN audit_reason TEXT DEFAULT ''")
        if "structured_json" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN structured_json TEXT")
        if "assistant_operation_key" not in resource_columns:
            statements.append("ALTER TABLE resources ADD COLUMN assistant_operation_key VARCHAR(120)")
        if not has_operation_unique("resources"):
            index_statements.append("CREATE UNIQUE INDEX IF NOT EXISTS uq_resources_assistant_operation_key ON resources (assistant_operation_key)")

    if "exercises" in table_names:
        exercise_columns = {column["name"] for column in inspector.get_columns("exercises")}
        if "assistant_operation_key" not in exercise_columns:
            statements.append("ALTER TABLE exercises ADD COLUMN assistant_operation_key VARCHAR(120)")
        if not has_operation_unique("exercises"):
            index_statements.append("CREATE UNIQUE INDEX IF NOT EXISTS uq_exercises_assistant_operation_key ON exercises (assistant_operation_key)")

    if "assistant_tasks" in table_names:
        task_columns = {column["name"] for column in inspector.get_columns("assistant_tasks")}
        if "worker_id" not in task_columns:
            statements.append("ALTER TABLE assistant_tasks ADD COLUMN worker_id VARCHAR(80)")
        if "execution_attempt" not in task_columns:
            statements.append("ALTER TABLE assistant_tasks ADD COLUMN execution_attempt INTEGER NOT NULL DEFAULT 0")
        if "heartbeat_at" not in task_columns:
            statements.append("ALTER TABLE assistant_tasks ADD COLUMN heartbeat_at DATETIME")
        if "started_at" not in task_columns:
            statements.append("ALTER TABLE assistant_tasks ADD COLUMN started_at DATETIME")
        if "next_attempt_at" not in task_columns:
            statements.append("ALTER TABLE assistant_tasks ADD COLUMN next_attempt_at DATETIME")

    if not statements and not index_statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        for statement in index_statements:
            connection.execute(text(statement))
