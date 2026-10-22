"""Add learning check-in, task occurrence and classroom attendance tables.

All three domains stay independent: autonomous check-ins, teacher check-in
tasks and classroom attendance never share a statistical denominator.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261022_0037"
down_revision = "20261022_0036"
branch_labels = None
depends_on = None

def _created_at():
    return sa.Column(
        "created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )


def _updated_at():
    return sa.Column(
        "updated_at",
        sa.DateTime(),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def upgrade():
    op.create_table(
        "study_checkin_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("knowledge_point", sa.String(160), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("problems", sa.Text(), nullable=False, server_default=""),
        sa.Column("checkin_date", sa.String(10), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="self"),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_study_checkin_logs_checkin_date", "study_checkin_logs", ["checkin_date"])
    op.create_index(
        "ix_study_checkin_user_date", "study_checkin_logs", ["user_id", "checkin_date"]
    )

    op.create_table(
        "checkin_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "class_id",
            sa.Integer(),
            sa.ForeignKey("classrooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("teacher_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("frequency", sa.String(16), nullable=False, server_default="once"),
        sa.Column("weekly_days", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("due_time", sa.String(5), nullable=False, server_default="23:59"),
        sa.Column("allow_late", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("review_mode", sa.String(8), nullable=False, server_default="manual"),
        sa.Column("require_attachment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("knowledge_points", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        _created_at(),
        _updated_at(),
    )
    for column in ["class_id", "course_id", "teacher_user_id", "status"]:
        op.create_index("ix_checkin_tasks_" + column, "checkin_tasks", [column])

    op.create_table(
        "checkin_task_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("checkin_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_key", sa.String(10), nullable=False),
        sa.Column("period_due_at", sa.DateTime(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("attachment_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="submitted"),
        sa.Column(
            "submitted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint(
            "task_id", "student_user_id", "period_key", name="uq_checkin_task_period_student"
        ),
    )
    for column in ["task_id", "student_user_id", "period_key", "status"]:
        op.create_index("ix_checkin_task_submissions_" + column, "checkin_task_submissions", [column])

    op.create_table(
        "checkin_submission_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.Integer(),
            sa.ForeignKey("checkin_task_submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False, server_default="update"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        _created_at(),
    )
    op.create_index(
        "ix_checkin_submission_revisions_submission_id",
        "checkin_submission_revisions",
        ["submission_id"],
    )

    op.create_table(
        "attendance_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "class_id",
            sa.Integer(),
            sa.ForeignKey("classrooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("teacher_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("late_after_at", sa.DateTime(), nullable=True),
        sa.Column("code", sa.String(8), nullable=False, unique=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        _created_at(),
        _updated_at(),
    )
    for column in ["class_id", "course_id", "teacher_user_id", "status"]:
        op.create_index("ix_attendance_sessions_" + column, "attendance_sessions", [column])

    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="present"),
        sa.Column("checked_in_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="code"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint(
            "session_id", "student_user_id", name="uq_attendance_session_student"
        ),
    )
    for column in ["session_id", "student_user_id", "status"]:
        op.create_index("ix_attendance_records_" + column, "attendance_records", [column])

    op.create_table(
        "checkin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("before_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("after_json", sa.JSON(), nullable=False, server_default="{}"),
        _created_at(),
    )
    for column in ["actor_user_id", "action"]:
        op.create_index("ix_checkin_audit_logs_" + column, "checkin_audit_logs", [column])


def downgrade():
    op.drop_table("checkin_audit_logs")
    op.drop_table("attendance_records")
    op.drop_table("attendance_sessions")
    op.drop_table("checkin_submission_revisions")
    op.drop_table("checkin_task_submissions")
    op.drop_table("checkin_tasks")
    op.drop_table("study_checkin_logs")
