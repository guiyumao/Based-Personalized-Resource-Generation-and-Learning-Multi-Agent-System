"""Add per-user activity lease and server-time evidence intervals."""

import sqlalchemy as sa
from alembic import op

revision = "20261020_0026"
down_revision = "20261019_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_sessions",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tab_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "study_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=False),
        sa.Column("page", sa.String(40), nullable=False),
    )
    for column in ("user_id", "started_at", "ended_at"):
        op.create_index(f"ix_study_activities_{column}", "study_activities", [column])


def downgrade() -> None:
    op.drop_table("study_activities")
    op.drop_table("study_sessions")
