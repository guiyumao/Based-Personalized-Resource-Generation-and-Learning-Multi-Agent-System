"""Persist administrator knowledge maintenance plans."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261018_0018"
down_revision = "20261018_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_maintenance_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("interval_hours", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_task_id", sa.Integer(), sa.ForeignKey("knowledge_build_tasks.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_knowledge_maintenance_plans_actor_user_id", "knowledge_maintenance_plans", ["actor_user_id"])
    op.create_index("ix_knowledge_maintenance_plans_next_run_at", "knowledge_maintenance_plans", ["next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_maintenance_plans_next_run_at", table_name="knowledge_maintenance_plans")
    op.drop_index("ix_knowledge_maintenance_plans_actor_user_id", table_name="knowledge_maintenance_plans")
    op.drop_table("knowledge_maintenance_plans")

