"""Carry budget enforcement across child tasks and reserve configured costs."""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0025"
down_revision = "20261019_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_build_tasks") as batch:
        batch.add_column(sa.Column("parent_task_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_knowledge_task_parent", "knowledge_build_tasks", ["parent_task_id"], ["id"])
    with op.batch_alter_table("knowledge_budget_counters") as batch:
        batch.add_column(sa.Column("reserved_cost_micros", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("knowledge_budget_counters") as batch:
        batch.drop_column("reserved_cost_micros")
    with op.batch_alter_table("knowledge_build_tasks") as batch:
        batch.drop_constraint("fk_knowledge_task_parent", type_="foreignkey")
        batch.drop_column("parent_task_id")
