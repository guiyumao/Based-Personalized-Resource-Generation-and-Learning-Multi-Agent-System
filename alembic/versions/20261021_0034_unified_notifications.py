"""Extend existing notifications without changing historical read state."""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0034"
down_revision = "20261021_0033"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        # Additive DDL keeps existing row IDs and avoids rebuilding an active inbox.
        op.execute("ALTER TABLE notifications ADD COLUMN sender_id INTEGER REFERENCES users(id)")
        op.execute("ALTER TABLE notifications ADD COLUMN event_key VARCHAR(160)")
        op.execute("ALTER TABLE notifications ADD COLUMN read_at DATETIME")
        op.create_index(
            "uq_notification_user_event", "notifications", ["user_id", "event_key"], unique=True
        )
    else:
        with op.batch_alter_table("notifications") as batch:
            batch.add_column(sa.Column("sender_id", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("event_key", sa.String(160), nullable=True))
            batch.add_column(sa.Column("read_at", sa.DateTime(), nullable=True))
            batch.create_foreign_key("fk_notification_sender", "users", ["sender_id"], ["id"])
            batch.create_unique_constraint("uq_notification_user_event", ["user_id", "event_key"])
    op.create_index("ix_notification_inbox", "notifications", ["user_id", "is_read", "id"])
    op.create_table(
        "notification_dispatches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", sa.String(80), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("sender_id", "request_key", name="uq_dispatch_request"),
    )


def downgrade():
    op.drop_table("notification_dispatches")
    sqlite = op.get_bind().dialect.name == "sqlite"
    with op.batch_alter_table("notifications") as batch:
        batch.drop_index("ix_notification_inbox")
        if sqlite:
            batch.drop_index("uq_notification_user_event")
        else:
            batch.drop_constraint("uq_notification_user_event", type_="unique")
            batch.drop_constraint("fk_notification_sender", type_="foreignkey")
        for name in ("read_at", "event_key", "sender_id"):
            batch.drop_column(name)
