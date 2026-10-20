"""Persist owner-scoped plan/task/resource selections and exercise membership."""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0028"
down_revision = "20261020_0027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_contexts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_request_id", sa.String(80), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("learning_paths.id"), nullable=False),
        sa.Column("module_id", sa.String(120), nullable=False),
        sa.Column("task_key", sa.String(120), nullable=False),
        sa.Column(
            "knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id"), nullable=False
        ),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id")),
        sa.Column("resource_version", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.UniqueConstraint("user_id", "client_request_id", name="uq_learning_context_request"),
    )
    op.create_index("ix_learning_contexts_user_id", "learning_contexts", ["user_id"])
    op.create_index("ix_learning_contexts_plan_id", "learning_contexts", ["plan_id"])
    op.create_table(
        "context_exercises",
        sa.Column(
            "context_id", sa.String(36), sa.ForeignKey("learning_contexts.id"), primary_key=True
        ),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), primary_key=True),
        sa.Column(
            "generation_task_id", sa.Integer(), sa.ForeignKey("assistant_tasks.id"), nullable=False
        ),
        sa.Column("feedback_json", sa.JSON()),
    )
    with op.batch_alter_table("study_notes") as batch:
        batch.add_column(sa.Column("learning_context_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_note_learning_context", "learning_contexts", ["learning_context_id"], ["id"]
        )
        batch.add_column(sa.Column("source_resource_version", sa.String(64)))
        batch.add_column(sa.Column("source_locator", sa.String(300)))


def downgrade():
    with op.batch_alter_table("study_notes") as batch:
        batch.drop_constraint("fk_note_learning_context", type_="foreignkey")
        for column in ("source_locator", "source_resource_version", "learning_context_id"):
            batch.drop_column(column)
    op.drop_table("context_exercises")
    op.drop_table("learning_contexts")
