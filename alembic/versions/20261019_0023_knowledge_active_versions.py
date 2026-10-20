"""Track effective knowledge versions and resource review impact."""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0023"
down_revision = "20261019_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_versions") as batch:
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("resources") as batch:
        batch.add_column(sa.Column("knowledge_versions_json", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("knowledge_review_required", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("resources") as batch:
        batch.drop_column("knowledge_review_required")
        batch.drop_column("knowledge_versions_json")
    with op.batch_alter_table("knowledge_versions") as batch:
        batch.drop_column("is_active")
