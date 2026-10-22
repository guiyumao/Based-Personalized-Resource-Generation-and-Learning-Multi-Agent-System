"""Teacher course deliveries and personalized reinforcement drafts."""
from alembic import op
from common.models.teacher_support import (
    CourseResourceDelivery,
    ReinforcementAttempt,
    ReinforcementDraft,
)

revision = "20261022_0041"
down_revision = "20261022_0040"
branch_labels = None
depends_on = None


def upgrade():
    CourseResourceDelivery.__table__.create(op.get_bind(), checkfirst=True)
    ReinforcementDraft.__table__.create(op.get_bind(), checkfirst=True)
    ReinforcementAttempt.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    ReinforcementAttempt.__table__.drop(op.get_bind(), checkfirst=True)
    ReinforcementDraft.__table__.drop(op.get_bind(), checkfirst=True)
    CourseResourceDelivery.__table__.drop(op.get_bind(), checkfirst=True)
