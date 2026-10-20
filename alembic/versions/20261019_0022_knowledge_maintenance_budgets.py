"""Persist bounded maintenance policies and shared usage reservations."""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0022"
down_revision = "20261019_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_maintenance_plans") as batch:
        batch.add_column(sa.Column("policy_json", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table("knowledge_budget_counters",
                    sa.Column("scope_key", sa.String(100), primary_key=True),
                    *(sa.Column(name, sa.Integer(), nullable=False, server_default="0")
                      for name in ("search_calls", "fetch_calls", "model_calls", "input_tokens", "output_tokens")))


def downgrade() -> None:
    op.drop_table("knowledge_budget_counters")
    with op.batch_alter_table("knowledge_maintenance_plans") as batch:
        batch.drop_column("policy_json")
