"""Require recorded publication permission and preserve its provenance."""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0024"
down_revision = "20261019_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("knowledge_candidates", "knowledge_versions"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("license_name", sa.String(100), nullable=False, server_default=""))
            batch.add_column(sa.Column("license_evidence_url", sa.Text(), nullable=False, server_default=""))
            if table == "knowledge_candidates":
                batch.add_column(sa.Column("publication_allowed", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for table in ("knowledge_versions", "knowledge_candidates"):
        with op.batch_alter_table(table) as batch:
            if table == "knowledge_candidates":
                batch.drop_column("publication_allowed")
            batch.drop_column("license_evidence_url")
            batch.drop_column("license_name")
