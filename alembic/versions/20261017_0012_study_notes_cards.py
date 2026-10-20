"""Private learner notes and review cards."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_0012"
down_revision = "20261017_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_study_notes_user_id", "study_notes", ["user_id"])
    op.create_table(
        "review_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("front", sa.String(length=500), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("source_note_id", sa.Integer(), sa.ForeignKey("study_notes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_review_cards_user_id", "review_cards", ["user_id"])
    op.create_index("ix_review_cards_due_at", "review_cards", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_review_cards_due_at", table_name="review_cards")
    op.drop_index("ix_review_cards_user_id", table_name="review_cards")
    op.drop_table("review_cards")
    op.drop_index("ix_study_notes_user_id", table_name="study_notes")
    op.drop_table("study_notes")

