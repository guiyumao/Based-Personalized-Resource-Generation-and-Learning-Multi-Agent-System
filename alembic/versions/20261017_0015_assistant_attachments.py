"""Persist text extracted from learner-uploaded assistant documents."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_0015"
down_revision = "20261017_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_assistant_attachments_user_id", "assistant_attachments", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_assistant_attachments_user_id", table_name="assistant_attachments")
    op.drop_table("assistant_attachments")
