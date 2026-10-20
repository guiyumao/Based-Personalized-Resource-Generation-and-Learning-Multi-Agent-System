"""Persist assistant tasks and their agent execution summaries."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_0011"
down_revision = "20261016_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=False),
        sa.Column("client_request_id", sa.String(80), nullable=False),
        sa.Column("task_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_step", sa.String(100), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "client_request_id", name="uq_assistant_task_request"),
    )
    op.create_index("ix_assistant_tasks_user_id", "assistant_tasks", ["user_id"])
    op.create_index("ix_assistant_tasks_session_id", "assistant_tasks", ["session_id"])
    op.create_index("ix_assistant_tasks_status", "assistant_tasks", ["status"])
    op.create_table(
        "assistant_agent_executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("assistant_tasks.id"), nullable=False),
        sa.Column("agent_code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_assistant_agent_executions_task_id", "assistant_agent_executions", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_assistant_agent_executions_task_id", table_name="assistant_agent_executions")
    op.drop_table("assistant_agent_executions")
    op.drop_index("ix_assistant_tasks_status", table_name="assistant_tasks")
    op.drop_index("ix_assistant_tasks_session_id", table_name="assistant_tasks")
    op.drop_index("ix_assistant_tasks_user_id", table_name="assistant_tasks")
    op.drop_table("assistant_tasks")
