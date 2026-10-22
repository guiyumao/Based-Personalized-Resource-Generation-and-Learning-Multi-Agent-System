"""Add the student-facing classroom plaza join mode.

``invite`` keeps the existing invitation-code enrollment; ``open`` lets a
student self-enroll from the classroom plaza. Existing classes default to
``invite`` so no current access rule changes silently.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261022_0038"
down_revision = "20261022_0037"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("classrooms") as batch:
        batch.add_column(
            sa.Column(
                "join_mode",
                sa.String(16),
                nullable=False,
                server_default="invite",
            )
        )


def downgrade():
    with op.batch_alter_table("classrooms") as batch:
        batch.drop_column("join_mode")
