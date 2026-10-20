"""Keep assistant resource and exercise writes unique across task retries."""

import sqlalchemy as sa
from alembic import op

revision = "20261018_0017"
down_revision = "20261018_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    task_columns = {column["name"] for column in inspector.get_columns("assistant_tasks")}
    with op.batch_alter_table("assistant_tasks") as batch:
        if "worker_id" not in task_columns:
            batch.add_column(sa.Column("worker_id", sa.String(80), nullable=True))
        if "execution_attempt" not in task_columns:
            batch.add_column(sa.Column("execution_attempt", sa.Integer(), nullable=False, server_default="0"))
        if "heartbeat_at" not in task_columns:
            batch.add_column(sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
        if "started_at" not in task_columns:
            batch.add_column(sa.Column("started_at", sa.DateTime(), nullable=True))
        if "next_attempt_at" not in task_columns:
            batch.add_column(sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
    for table in ("resources", "exercises"):
        columns = {column["name"] for column in inspector.get_columns(table)}
        unique = any("assistant_operation_key" in constraint.get("column_names", [])
                     for constraint in inspector.get_unique_constraints(table)) or any(
            index.get("unique") and "assistant_operation_key" in index.get("column_names", [])
            for index in inspector.get_indexes(table)
        )
        with op.batch_alter_table(table) as batch:
            if "assistant_operation_key" not in columns:
                batch.add_column(sa.Column("assistant_operation_key", sa.String(120), nullable=True))
            if not unique:
                batch.create_unique_constraint(f"uq_{table}_assistant_operation_key", ["assistant_operation_key"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in ("exercises", "resources"):
        name = f"uq_{table}_assistant_operation_key"
        indexes = {index["name"] for index in inspector.get_indexes(table)}
        if name in indexes:
            op.drop_index(name, table_name=table)
        with op.batch_alter_table(table) as batch:
            if name not in indexes:
                batch.drop_constraint(name, type_="unique")
            batch.drop_column("assistant_operation_key")
    for column in ("next_attempt_at", "started_at", "heartbeat_at", "execution_attempt", "worker_id"):
        op.drop_column("assistant_tasks", column)
