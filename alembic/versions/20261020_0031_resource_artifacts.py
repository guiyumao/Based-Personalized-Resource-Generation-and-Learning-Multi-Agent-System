"""Version-bound artifacts and immutable resource edit snapshots."""
import sqlalchemy as sa

from alembic import op

revision = "20261020_0031"
down_revision = "20261020_0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("resource_artifacts", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("context_id", sa.String(36), sa.ForeignKey("learning_contexts.id"), nullable=False),
        sa.Column("resource_version", sa.String(64), nullable=False), sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("relative_path", sa.String(240), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("context_id", "kind", name="uq_context_artifact_kind"))
    op.create_index("ix_resource_artifacts_user_id", "resource_artifacts", ["user_id"])
    op.create_table("resource_revisions", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.String(64), nullable=False), sa.Column("title", sa.String(200)),
        sa.Column("content", sa.Text(), nullable=False), sa.Column("structured_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("resource_id", "version", name="uq_resource_revision_version"))
    op.create_index("ix_resource_revisions_resource_id", "resource_revisions", ["resource_id"])


def downgrade():
    op.drop_table("resource_revisions")
    op.drop_table("resource_artifacts")
