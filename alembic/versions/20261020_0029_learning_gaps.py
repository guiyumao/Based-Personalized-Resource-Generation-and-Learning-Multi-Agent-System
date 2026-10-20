"""Persist learning coverage requests without publishing model-created knowledge."""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0029"
down_revision = "20261020_0028"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_knowledge_gaps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", sa.String(64), nullable=False, unique=True),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("knowledge_point", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("knowledge_task_id", sa.Integer(), sa.ForeignKey("knowledge_build_tasks.id")),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
    )
    op.create_index("ix_learning_knowledge_gaps_user_id", "learning_knowledge_gaps", ["user_id"])


def downgrade():
    op.drop_table("learning_knowledge_gaps")
