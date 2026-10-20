"""Store learner-confirmed assistant memory with user and course isolation."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_0013"
down_revision = "20261017_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_key", sa.String(100), nullable=False, server_default=""),
        sa.Column("memory_type", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.String(100), nullable=False, server_default="user_confirmed"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_assistant_memories_user_id", "assistant_memories", ["user_id"])
    op.create_index("ix_assistant_memories_course_key", "assistant_memories", ["course_key"])


def downgrade() -> None:
    op.drop_index("ix_assistant_memories_course_key", table_name="assistant_memories")
    op.drop_index("ix_assistant_memories_user_id", table_name="assistant_memories")
    op.drop_table("assistant_memories")
