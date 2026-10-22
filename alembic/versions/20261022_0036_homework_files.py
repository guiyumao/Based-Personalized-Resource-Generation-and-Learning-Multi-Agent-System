"""Add private homework originals without rewriting existing submissions."""

import sqlalchemy as sa

from alembic import op

revision = "20261022_0036"
down_revision = "20261022_0035"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "homework_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Integer(),
            sa.ForeignKey("assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("student_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "submission_id",
            sa.Integer(),
            sa.ForeignKey("assignment_submissions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(100), nullable=False, unique=True),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    for column in ["assignment_id", "student_user_id", "submission_id"]:
        op.create_index("ix_homework_attachments_" + column, "homework_attachments", [column])


def downgrade():
    op.drop_table("homework_attachments")
