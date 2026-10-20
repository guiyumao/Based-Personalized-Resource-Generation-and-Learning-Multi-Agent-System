"""Extend the existing subject and knowledge point catalog for confirmed outlines."""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0021"
down_revision = "20261019_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("system_subjects") as batch:
        batch.add_column(sa.Column("code", sa.String(100), nullable=True))
        batch.add_column(sa.Column("aliases_json", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("outline_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("construction_status", sa.String(24), nullable=False, server_default="PLANNED"))
        batch.create_unique_constraint("uq_system_subject_code", ["code"])
    with op.batch_alter_table("knowledge_points") as batch:
        batch.add_column(sa.Column("chapter", sa.String(160), nullable=False, server_default=""))
        for name in ("aliases_json", "objectives_json", "prerequisites_json"):
            batch.add_column(sa.Column(name, sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("construction_status", sa.String(24), nullable=False, server_default="PLANNED"))


def downgrade() -> None:
    with op.batch_alter_table("knowledge_points") as batch:
        for name in ("construction_status", "prerequisites_json", "objectives_json", "aliases_json", "chapter"):
            batch.drop_column(name)
    with op.batch_alter_table("system_subjects") as batch:
        batch.drop_constraint("uq_system_subject_code", type_="unique")
        for name in ("construction_status", "outline_json", "aliases_json", "code"):
            batch.drop_column(name)
