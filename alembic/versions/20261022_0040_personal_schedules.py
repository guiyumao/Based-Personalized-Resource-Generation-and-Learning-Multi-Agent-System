"""Private student timetable additions and occurrence overrides."""

from alembic import op
from common.models.checkin import PersonalSchedule

revision = "20261022_0040"
down_revision = "20261022_0039"
branch_labels = None
depends_on = None


def upgrade():
    PersonalSchedule.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    PersonalSchedule.__table__.drop(op.get_bind(), checkfirst=True)
