"""Adapt original corpus and uploads to subject/point metadata."""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0027"
down_revision = "20261020_0026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("corpus_path", sa.Text(), nullable=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("system_subjects.id"), nullable=True),
        sa.Column("chapter", sa.String(160), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("creator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "candidate_id", sa.Integer(), sa.ForeignKey("knowledge_candidates.id"), nullable=True
        ),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_knowledge_documents_subject_id", "knowledge_documents", ["subject_id"])
    op.create_table(
        "knowledge_document_points",
        sa.Column(
            "document_id", sa.String(32), sa.ForeignKey("knowledge_documents.id"), primary_key=True
        ),
        sa.Column("point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id"), primary_key=True),
    )


def downgrade():
    op.drop_table("knowledge_document_points")
    op.drop_table("knowledge_documents")
