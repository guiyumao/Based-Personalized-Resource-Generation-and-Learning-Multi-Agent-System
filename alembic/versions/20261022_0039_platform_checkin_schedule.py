"""Platform daily check-ins, classroom metadata and course schedule.

The platform check-in is independent from classrooms and attendance: it has no
class/course reference and allows at most one row per user per business day.
The superseded multi-record ``study_checkin_logs`` table is intentionally left
untouched by the migration; the deployment script removes it only when it has
no rows belonging to existing users.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261022_0039"
down_revision = "20261022_0038"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("classrooms") as batch:
        batch.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("objective", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("syllabus", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("semester", sa.String(40), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(
            sa.Column("capacity", sa.Integer(), nullable=False, server_default="0")
        )

    op.create_table(
        "platform_daily_checkins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("checkin_date", sa.String(10), nullable=False),
        sa.Column(
            "checkin_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "timezone", sa.String(40), nullable=False, server_default="Asia/Shanghai"
        ),
        sa.Column("goal", sa.Text(), nullable=False, server_default=""),
        sa.Column("reflection", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("user_id", "checkin_date", name="uq_platform_checkin_user_day"),
    )
    op.create_index(
        "ix_platform_daily_checkins_checkin_date", "platform_daily_checkins", ["checkin_date"]
    )
    op.create_index(
        "ix_platform_checkin_user_date", "platform_daily_checkins", ["user_id", "checkin_date"]
    )

    op.create_table(
        "class_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "class_id",
            sa.Integer(),
            sa.ForeignKey("classrooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("teacher_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("topic", sa.String(160), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(5), nullable=False),
        sa.Column("end_time", sa.String(5), nullable=False),
        sa.Column("week_start", sa.String(10), nullable=False),
        sa.Column("week_end", sa.String(10), nullable=False),
        sa.Column("location", sa.String(160), nullable=False, server_default=""),
        sa.Column("mode", sa.String(16), nullable=False, server_default="offline"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    for column in ["class_id", "teacher_user_id"]:
        op.create_index("ix_class_sessions_" + column, "class_sessions", [column])

    op.create_table(
        "class_schedule_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("class_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            sa.Integer(),
            sa.ForeignKey("classrooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("teacher_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("new_date", sa.String(10), nullable=True),
        sa.Column("new_start_time", sa.String(5), nullable=True),
        sa.Column("new_end_time", sa.String(5), nullable=True),
        sa.Column("location", sa.String(160), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("session_id", "date", name="uq_schedule_exception_session_date"),
    )
    for column in ["session_id", "class_id", "date"]:
        op.create_index(
            "ix_class_schedule_exceptions_" + column, "class_schedule_exceptions", [column]
        )


def downgrade():
    op.drop_table("class_schedule_exceptions")
    op.drop_table("class_sessions")
    op.drop_table("platform_daily_checkins")
    with op.batch_alter_table("classrooms") as batch:
        for column in [
            "description",
            "objective",
            "syllabus",
            "semester",
            "is_public",
            "capacity",
        ]:
            batch.drop_column(column)
