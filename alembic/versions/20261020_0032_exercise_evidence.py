"""Explicit confirmed exercise knowledge-point membership."""
import sqlalchemy as sa

from alembic import op

revision = "20261020_0032"
down_revision = "20261020_0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("exercise_knowledge_points",
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), primary_key=True),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id"), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False))


def downgrade():
    op.drop_table("exercise_knowledge_points")
