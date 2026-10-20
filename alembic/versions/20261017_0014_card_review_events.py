"""Record each flashcard review and its scheduled next due time."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_0014"
down_revision = "20261017_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_review_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("review_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("next_due_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_card_review_events_user_id", "card_review_events", ["user_id"])
    op.create_index("ix_card_review_events_card_id", "card_review_events", ["card_id"])
    op.create_index("ix_card_review_events_reviewed_at", "card_review_events", ["reviewed_at"])


def downgrade() -> None:
    op.drop_index("ix_card_review_events_reviewed_at", table_name="card_review_events")
    op.drop_index("ix_card_review_events_card_id", table_name="card_review_events")
    op.drop_index("ix_card_review_events_user_id", table_name="card_review_events")
    op.drop_table("card_review_events")
