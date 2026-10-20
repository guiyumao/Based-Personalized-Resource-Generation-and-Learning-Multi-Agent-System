"""Persist learner exercise favorites."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261016_0010"
down_revision = "20261016_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exercise_favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_point", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("question_type", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("difficulty", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("analysis", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "exercise_id", name="uq_exercise_favorite_user_exercise"),
    )
    op.create_index("ix_exercise_favorites_user_id", "exercise_favorites", ["user_id"])
    op.create_index("ix_exercise_favorites_exercise_id", "exercise_favorites", ["exercise_id"])


def downgrade() -> None:
    op.drop_index("ix_exercise_favorites_exercise_id", table_name="exercise_favorites")
    op.drop_index("ix_exercise_favorites_user_id", table_name="exercise_favorites")
    op.drop_table("exercise_favorites")
