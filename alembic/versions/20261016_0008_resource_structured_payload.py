"""Add the structured resource payload column.

``mind_map`` / ``code_case`` / ``video_script`` resources keep their typed
payload (and the deterministic validation report produced for it) next to the
rendered Markdown so readers can render the real structure. The column is
nullable, so every pre-existing row stays valid and no backfill is required.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261016_0008"
down_revision = "20261014_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("structured_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("resources", "structured_json")
