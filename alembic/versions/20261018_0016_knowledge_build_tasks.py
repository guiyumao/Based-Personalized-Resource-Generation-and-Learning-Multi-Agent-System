"""Persist unified knowledge build tasks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261018_0016"
down_revision = "20261017_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_build_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_request_id", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("trigger_source", sa.String(40), nullable=False),
        sa.Column("operation_type", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("requirements_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_step", sa.String(100), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("actor_user_id", "client_request_id", name="uq_knowledge_build_task_request"),
    )
    op.create_index("ix_knowledge_build_tasks_actor_user_id", "knowledge_build_tasks", ["actor_user_id"])
    op.create_index("ix_knowledge_build_tasks_status", "knowledge_build_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_build_tasks_status", table_name="knowledge_build_tasks")
    op.drop_index("ix_knowledge_build_tasks_actor_user_id", table_name="knowledge_build_tasks")
    op.drop_table("knowledge_build_tasks")
