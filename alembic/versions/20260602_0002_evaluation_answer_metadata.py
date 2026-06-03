"""Add evaluation metadata columns to answer_records."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260602_0002"
down_revision = "20260528_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Extend answer records with evaluation payload metadata."""

    op.add_column("answer_records", sa.Column("evaluation_json", sa.JSON(), nullable=True))
    op.add_column("answer_records", sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove evaluation metadata columns."""

    op.drop_column("answer_records", "created_at")
    op.drop_column("answer_records", "evaluation_json")
