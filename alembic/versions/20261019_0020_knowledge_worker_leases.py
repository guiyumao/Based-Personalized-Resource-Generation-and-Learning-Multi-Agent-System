"""Fence knowledge worker writes with bounded renewable leases."""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0020"
down_revision = "20261019_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_build_tasks") as batch:
        batch.add_column(sa.Column("worker_id", sa.String(80), nullable=True))
        batch.add_column(sa.Column("execution_attempt", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("knowledge_build_tasks") as batch:
        for name in ("next_attempt_at", "cancel_requested", "lease_expires_at", "heartbeat_at", "execution_attempt", "worker_id"):
            batch.drop_column(name)
