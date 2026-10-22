"""Apply the check-in, classroom-plaza and schedule schema to an existing database.

The shared local SQLite database has no trusted Alembic baseline, so deployment
uses ``Base.metadata.create_all`` (idempotent, additive) plus explicit
``ALTER TABLE ... ADD COLUMN`` after a manual backup. Only the deprecated,
empty ``study_checkin_logs`` table is dropped; non-empty data is never removed.

Usage:
    set DATABASE_URL=sqlite+pysqlite:///.../runtime.sqlite
    python scripts/apply_checkin_schema.py
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from common.config import get_settings
from common.db.base import Base
from common.models import checkin, learning, media, operations, study  # noqa: F401

EXPECTED_TABLES = (
    "platform_daily_checkins",
    "checkin_tasks",
    "checkin_task_submissions",
    "checkin_submission_revisions",
    "attendance_sessions",
    "attendance_records",
    "checkin_audit_logs",
    "class_sessions",
    "class_schedule_exceptions",
)

CLASSROOM_COLUMNS = {
    "join_mode": "VARCHAR(16) NOT NULL DEFAULT 'invite'",
    "description": "TEXT NOT NULL DEFAULT ''",
    "objective": "TEXT NOT NULL DEFAULT ''",
    "syllabus": "TEXT NOT NULL DEFAULT ''",
    "semester": "VARCHAR(40) NOT NULL DEFAULT ''",
    "is_public": "BOOLEAN NOT NULL DEFAULT 1",
    "capacity": "INTEGER NOT NULL DEFAULT 0",
}


def _ensure_classroom_columns(engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("classrooms")}
    with engine.begin() as connection:
        for name, ddl in CLASSROOM_COLUMNS.items():
            if name in columns:
                print(f"classrooms.{name}: present")
                continue
            connection.execute(text(f"ALTER TABLE classrooms ADD COLUMN {name} {ddl}"))
            print(f"classrooms.{name}: added")


def _drop_legacy_checkin_table(engine, tables: set[str]) -> None:
    if "study_checkin_logs" not in tables:
        print("study_checkin_logs: absent")
        return
    with engine.begin() as connection:
        total = connection.execute(text("SELECT COUNT(*) FROM study_checkin_logs")).scalar_one()
        orphaned = connection.execute(
            text(
                "SELECT COUNT(*) FROM study_checkin_logs l "
                "LEFT JOIN users u ON u.id = l.user_id WHERE u.id IS NULL"
            )
        ).scalar_one()
        valid = total - orphaned
        if valid:
            print(
                f"study_checkin_logs: kept ({valid} rows belong to existing users; "
                "manual review required)"
            )
            return
        if orphaned:
            print(f"study_checkin_logs: removing {orphaned} orphaned test rows")
        connection.execute(text("DROP TABLE study_checkin_logs"))
    print("study_checkin_logs: dropped (no existing-user rows)")


def main() -> None:
    engine = create_engine(get_settings().database_url, future=True)
    before = set(inspect(engine).get_table_names())
    missing = [name for name in EXPECTED_TABLES if name not in before]
    print("missing before:", missing or "none")
    Base.metadata.create_all(bind=engine)
    after = set(inspect(engine).get_table_names())
    print(
        "created:",
        [name for name in EXPECTED_TABLES if name not in before and name in after] or "none",
    )
    print("present:", [name for name in EXPECTED_TABLES if name in after])
    _ensure_classroom_columns(engine)
    _drop_legacy_checkin_table(engine, after)


if __name__ == "__main__":
    main()
