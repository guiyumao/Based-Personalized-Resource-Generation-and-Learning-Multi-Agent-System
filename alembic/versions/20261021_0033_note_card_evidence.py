"""Private note snapshots and flashcard source/replay evidence, without changing old columns."""
import sqlalchemy as sa

from alembic import op

revision = "20261021_0033"
down_revision = "20261020_0032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('note_revisions',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('note_id',sa.Integer(),sa.ForeignKey('study_notes.id',ondelete='CASCADE'),nullable=False),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('version',sa.String(64),nullable=False),sa.Column('snapshot_json',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_note_revisions_note_id','note_revisions',['note_id'])
    op.create_index('ix_note_revisions_user_id','note_revisions',['user_id'])
    op.create_table('card_knowledge_bindings',sa.Column('card_id',sa.Integer(),sa.ForeignKey('review_cards.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('knowledge_point_id',sa.Integer(),sa.ForeignKey('knowledge_points.id'),nullable=False),
        sa.Column('context_id',sa.String(36),sa.ForeignKey('learning_contexts.id'),nullable=True),
        sa.Column('resource_id',sa.Integer(),sa.ForeignKey('resources.id'),nullable=True),
        sa.Column('resource_version',sa.String(64),nullable=True))
    op.create_index('ix_card_knowledge_bindings_user_id','card_knowledge_bindings',['user_id'])
    op.create_table('card_review_receipts',sa.Column('request_id',sa.String(80),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),primary_key=True),
        sa.Column('card_id',sa.Integer(),sa.ForeignKey('review_cards.id',ondelete='CASCADE'),nullable=False),
        sa.Column('event_id',sa.Integer(),sa.ForeignKey('card_review_events.id',ondelete='CASCADE'),nullable=False),
        sa.Column('grade',sa.Integer(),nullable=False))


def downgrade():
    for table in ("card_review_receipts", "card_knowledge_bindings", "note_revisions"):
        op.drop_table(table)
