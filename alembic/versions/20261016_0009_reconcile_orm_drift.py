"""Reconcile the migrated schema with the ORM models.

The Alembic chain created ``resources`` without ``title``/``source_url``/
``local_path``/``tags``/``crawl_status``/``language``/``summary`` and never added
``user_profiles.profile_analysis`` or
``answer_records.evaluation_json``/``created_at``.  Those columns exist in
``common/models/learning.py`` and were only ever created on a development SQLite
file by ``Base.metadata.create_all`` plus the ``_ensure_legacy_columns`` patch.

A freshly migrated PostgreSQL database was therefore **missing columns the ORM
selects**, so the first write failed with ``UndefinedColumn`` while the running
service silently papered over the gap at startup.  This migration closes that
drift for real databases.

Every statement is guarded by an inspector check, so the revision is a no-op for
a database that already has the columns (for example a SQLite file created by
``create_all`` before Alembic was ever run against it) and is safe to re-run
after a partial failure.  All added columns are nullable: existing rows must stay
valid and no backfill is required.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261016_0009"
down_revision = "20261016_0008"
branch_labels = None
depends_on = None


#: table -> [(column name, column type)] that the ORM requires.
REQUIRED_COLUMNS: dict[str, list[tuple[str, sa.types.TypeEngine]]] = {
    "resources": [
        ("title", sa.String(length=200)),
        ("source_url", sa.Text()),
        ("local_path", sa.Text()),
        ("tags", sa.JSON()),
        ("crawl_status", sa.String(length=20)),
        ("language", sa.String(length=10)),
        ("summary", sa.Text()),
    ],
    "user_profiles": [
        ("profile_analysis", sa.JSON()),
    ],
    "answer_records": [
        ("evaluation_json", sa.JSON()),
        ("created_at", sa.DateTime()),
    ],
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    for table, columns in REQUIRED_COLUMNS.items():
        if table not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name, column_type in columns:
            if name in present:
                continue
            op.add_column(table, sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    for table, columns in REQUIRED_COLUMNS.items():
        # Created by 0002; 0009 may repair absence but never owns removal.
        if table == "answer_records":
            continue
        if table not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name, _ in columns:
            if name in present:
                op.drop_column(table, name)
