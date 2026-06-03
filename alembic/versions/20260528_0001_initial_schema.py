"""Initial schema for personalized learning system."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260528_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial relational schema."""

    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("subject_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_knowledge_points_id", "knowledge_points", ["id"], unique=False)
    op.create_index("ix_knowledge_points_name", "knowledge_points", ["name"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="student"),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True, nullable=False),
        sa.Column("mastery_json", sa.JSON(), nullable=False),
        sa.Column("learning_style", sa.String(length=20), nullable=False, server_default="VARK"),
        sa.Column("cognitive_abilities", sa.JSON(), nullable=False),
        sa.Column("habits", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "knowledge_relations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("from_id", sa.Integer(), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("to_id", sa.Integer(), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("relation_type", sa.String(length=30), nullable=False),
    )

    op.create_table(
        "resources",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False, server_default="markdown"),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id"), nullable=True),
        sa.Column("generated_for_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "learning_paths",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("path_data_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "learning_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("path_id", sa.Integer(), sa.ForeignKey("learning_paths.id"), nullable=False),
        sa.Column("task_type", sa.String(length=30), nullable=False),
        sa.Column("resource_ids", sa.JSON(), nullable=False),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("analysis", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "answer_records",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("time_spent", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "learning_reports",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("report_type", sa.String(length=20), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    """Drop the initial relational schema."""

    op.drop_table("learning_reports")
    op.drop_table("answer_records")
    op.drop_table("exercises")
    op.drop_table("learning_tasks")
    op.drop_table("learning_paths")
    op.drop_table("resources")
    op.drop_table("knowledge_relations")
    op.drop_table("user_profiles")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_knowledge_points_name", table_name="knowledge_points")
    op.drop_index("ix_knowledge_points_id", table_name="knowledge_points")
    op.drop_table("knowledge_points")
