"""Track learner interactions for explainable resource recommendations."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261010_0004"
down_revision = "20260916_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_interactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("knowledge_point", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resource_interactions_user_id", "resource_interactions", ["user_id"])
    op.create_index("ix_resource_interactions_resource_id", "resource_interactions", ["resource_id"])
    op.create_index("ix_resource_interactions_action", "resource_interactions", ["action"])
    op.create_index("ix_resource_interactions_knowledge_point", "resource_interactions", ["knowledge_point"])
    op.create_index("ix_resource_interactions_created_at", "resource_interactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_resource_interactions_created_at", table_name="resource_interactions")
    op.drop_index("ix_resource_interactions_knowledge_point", table_name="resource_interactions")
    op.drop_index("ix_resource_interactions_action", table_name="resource_interactions")
    op.drop_index("ix_resource_interactions_resource_id", table_name="resource_interactions")
    op.drop_index("ix_resource_interactions_user_id", table_name="resource_interactions")
    op.drop_table("resource_interactions")
