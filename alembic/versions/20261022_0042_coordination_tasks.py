"""Persistent asynchronous learning path requests."""
from alembic import op
from common.models.learning import CoordinationTask

revision = "20261022_0042"
down_revision = "20261022_0041"
branch_labels = None
depends_on = None


def upgrade():
    CoordinationTask.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    CoordinationTask.__table__.drop(op.get_bind(), checkfirst=True)
