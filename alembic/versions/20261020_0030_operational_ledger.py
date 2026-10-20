"""Durable provider call ledger and independent Worker process heartbeats."""
import sqlalchemy as sa

from alembic import op

revision = "20261020_0030"
down_revision = "20261020_0029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("model_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False), sa.Column("model", sa.String(160), nullable=False),
        sa.Column("response_model", sa.String(160)), sa.Column("mode", sa.String(12), nullable=False),
        sa.Column("feature", sa.String(160), nullable=False), sa.Column("user_id", sa.Integer()),
        sa.Column("request_id", sa.String(80)), sa.Column("task_kind", sa.String(24)), sa.Column("task_id", sa.Integer()),
        sa.Column("attempt", sa.Integer()), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("usage_status", sa.String(20), nullable=False), sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()), sa.Column("cached_input_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(80)), sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()), sa.Column("elapsed_ms", sa.Float()))
    for name in ("mode", "feature", "user_id", "task_id", "status", "started_at"):
        op.create_index(f"ix_model_calls_{name}", "model_calls", [name])
    op.create_table("worker_instances",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False), sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=False), sa.Column("stopped_at", sa.DateTime()),
        sa.Column("heartbeat_interval", sa.Integer(), nullable=False), sa.Column("batches", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80)))
    for name in ("kind", "heartbeat_at"):
        op.create_index(f"ix_worker_instances_{name}", "worker_instances", [name])
    op.create_table("task_attempts",
        sa.Column("task_kind", sa.String(24), primary_key=True), sa.Column("task_id", sa.Integer(), primary_key=True),
        sa.Column("attempt", sa.Integer(), primary_key=True), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False), sa.Column("finished_at", sa.DateTime()),
        sa.Column("error_code", sa.String(80)))


def downgrade():
    op.drop_table("task_attempts")
    op.drop_table("worker_instances")
    op.drop_table("model_calls")
