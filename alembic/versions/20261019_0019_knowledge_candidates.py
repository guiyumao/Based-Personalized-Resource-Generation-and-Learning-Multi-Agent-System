"""Persist reviewed candidates and immutable knowledge versions."""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0019"
down_revision = "20261018_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("creator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_task_id", sa.Integer(), sa.ForeignKey("knowledge_build_tasks.id"), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("knowledge_point", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("published_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_task_id", name="uq_knowledge_candidate_source_task"),
    )
    op.create_index("ix_knowledge_candidates_creator_user_id", "knowledge_candidates", ["creator_user_id"])
    op.create_index("ix_knowledge_candidates_status", "knowledge_candidates", ["status"])
    op.create_table(
        "knowledge_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("knowledge_candidates.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("knowledge_point", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("corpus_path", sa.Text(), nullable=False),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("candidate_id", "content_hash", name="uq_knowledge_version_candidate_content"),
    )
    op.create_index("ix_knowledge_versions_candidate_id", "knowledge_versions", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("knowledge_versions")
    op.drop_table("knowledge_candidates")
