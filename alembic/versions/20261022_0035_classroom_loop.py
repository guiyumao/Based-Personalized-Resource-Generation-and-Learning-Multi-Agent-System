"""Add class invitations/status and immutable submission history, preserving old rows."""

import secrets

import sqlalchemy as sa

from alembic import op

revision = "20261022_0035"
down_revision = "20261021_0034"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("classrooms", sa.Column("invite_code", sa.String(32), nullable=True))
    op.add_column(
        "classrooms", sa.Column("status", sa.String(20), nullable=False, server_default="active")
    )
    op.create_index("uq_classroom_invite", "classrooms", ["invite_code"], unique=True)
    connection = op.get_bind()
    for cid in connection.execute(sa.text("SELECT id FROM classrooms")).scalars().all():
        connection.execute(
            sa.text("UPDATE classrooms SET invite_code=:code WHERE id=:id"),
            {"id": cid, "code": secrets.token_hex(8).upper()},
        )
    op.create_table(
        "submission_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.Integer(),
            sa.ForeignKey("assignment_submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index(
        "ix_submission_revisions_submission_id", "submission_revisions", ["submission_id"]
    )


def downgrade():
    op.drop_table("submission_revisions")
    op.drop_index("uq_classroom_invite", table_name="classrooms")
    op.drop_column("classrooms", "status")
    op.drop_column("classrooms", "invite_code")
