"""Persist courses, classes, homework, discussions, notifications and admin state."""

from alembic import op
import sqlalchemy as sa

revision = "20261010_0005"
down_revision = "20261010_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("courses", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(120), nullable=False), sa.Column("subject", sa.String(100), nullable=False), sa.Column("description", sa.Text(), nullable=False, server_default=""), sa.Column("teacher_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="active"), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("classrooms", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(100), nullable=False), sa.Column("subject", sa.String(100), nullable=False), sa.Column("teacher_name", sa.String(100), nullable=False), sa.Column("teacher_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id")), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("class_enrollments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("class_id", sa.Integer(), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False), sa.Column("student_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.UniqueConstraint("class_id", "student_user_id", name="uq_class_student"))
    op.create_table("assignments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("class_id", sa.Integer(), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False), sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id")), sa.Column("teacher_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("due_at", sa.DateTime()), sa.Column("status", sa.String(20), nullable=False, server_default="published"), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("assignment_submissions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False), sa.Column("student_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("attachment_url", sa.Text()), sa.Column("status", sa.String(20), nullable=False, server_default="submitted"), sa.Column("submitted_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("score", sa.Float()), sa.Column("teacher_comment", sa.Text(), nullable=False, server_default=""), sa.Column("reviewed_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.UniqueConstraint("assignment_id", "student_user_id", name="uq_assignment_student"))
    op.create_table("discussion_threads", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("class_id", sa.Integer(), sa.ForeignKey("classrooms.id", ondelete="CASCADE")), sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id")), sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="open"), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("discussion_replies", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("thread_id", sa.Integer(), sa.ForeignKey("discussion_threads.id", ondelete="CASCADE"), nullable=False), sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("notifications", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("type", sa.String(30), nullable=False, server_default="system"), sa.Column("related_type", sa.String(30), nullable=False, server_default=""), sa.Column("related_id", sa.Integer()), sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("system_subjects", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True), sa.Column("description", sa.String(200), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("system_configs", sa.Column("key", sa.String(100), primary_key=True), sa.Column("value", sa.String(200), nullable=False), sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("audit_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("level", sa.String(20), nullable=False), sa.Column("event", sa.String(80), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))

    for table, columns in {
        "courses": ["teacher_user_id", "subject"], "classrooms": ["teacher_user_id", "course_id", "subject"],
        "class_enrollments": ["class_id", "student_user_id"], "assignments": ["class_id", "teacher_user_id", "status"],
        "assignment_submissions": ["assignment_id", "student_user_id", "status"], "discussion_threads": ["class_id", "author_user_id"],
        "discussion_replies": ["thread_id"], "notifications": ["user_id", "is_read"], "audit_logs": ["level", "event"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in ["audit_logs", "system_configs", "system_subjects", "notifications", "discussion_replies", "discussion_threads", "assignment_submissions", "assignments", "class_enrollments", "classrooms", "courses"]:
        op.drop_table(table)
