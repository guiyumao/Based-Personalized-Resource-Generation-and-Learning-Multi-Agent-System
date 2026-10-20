"""Separate resource generation, audit, and publication states."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260916_0003"
down_revision = "20260602_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column("generation_status", sa.String(length=20), nullable=False, server_default="generated"),
    )
    op.add_column(
        "resources",
        sa.Column("audit_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "resources",
        sa.Column("publish_status", sa.String(length=20), nullable=False, server_default="draft"),
    )
    op.add_column(
        "resources",
        sa.Column("audit_reason", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("resources", "audit_reason")
    op.drop_column("resources", "publish_status")
    op.drop_column("resources", "audit_status")
    op.drop_column("resources", "generation_status")
