"""Tests for database bootstrap scripts and ORM metadata."""

from sqlalchemy import inspect

from common.db.base import Base
from common.db.session import engine
from common.models import learning  # noqa: F401


def test_metadata_contains_expected_tables() -> None:
    """ORM metadata should define the core learning system tables."""

    expected_tables = {
        "users",
        "user_profiles",
        "knowledge_points",
        "knowledge_relations",
        "resources",
        "learning_paths",
        "learning_tasks",
        "exercises",
        "answer_records",
        "learning_reports",
        "teaching_scopes",
    }
    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_create_all_creates_tables() -> None:
    """`create_all` should create tables in the configured database."""

    Base.metadata.create_all(bind=engine)
    table_names = set(inspect(engine).get_table_names())
    assert "users" in table_names
    assert "learning_reports" in table_names
