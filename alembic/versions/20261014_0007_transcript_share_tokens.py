"""Add revocable opaque share tokens for transcript reports."""

from alembic import op
import sqlalchemy as sa

revision = "20261014_0007"
down_revision = "20261014_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transcript_analyses", sa.Column("share_token", sa.String(80), nullable=True))
    op.create_index("ix_transcript_analyses_share_token", "transcript_analyses", ["share_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_transcript_analyses_share_token", table_name="transcript_analyses")
    op.drop_column("transcript_analyses", "share_token")
