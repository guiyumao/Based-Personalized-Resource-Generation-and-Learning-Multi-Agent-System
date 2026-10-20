"""Persist transcript imports, normalized scores and multi-agent analyses."""

from alembic import op
import sqlalchemy as sa

revision = "20261014_0006"
down_revision = "20261010_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default="parsed"),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("field_mapping_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("normalized_rows_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_transcript_imports_owner_user_id", "transcript_imports", ["owner_user_id"])
    op.create_index("ix_transcript_imports_content_hash", "transcript_imports", ["content_hash"])
    op.create_table(
        "transcript_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_id", sa.Integer(), sa.ForeignKey("transcript_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("student_no", sa.String(80), nullable=False, server_default=""),
        sa.Column("student_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("class_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("subject", sa.String(100), nullable=False, server_default=""),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False, server_default="100"),
        sa.Column("exam_date", sa.String(30)),
        sa.Column("chapter", sa.String(160), nullable=False, server_default=""),
        sa.Column("question_scores_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("confidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("raw_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    for column in ["import_id", "student_user_id", "student_no", "student_name", "class_name", "subject"]:
        op.create_index(f"ix_transcript_scores_{column}", "transcript_scores", [column])
    op.create_table(
        "transcript_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_id", sa.Integer(), sa.ForeignKey("transcript_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False, server_default="student"),
        sa.Column("cache_key", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("report_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("data_quality", sa.String(20), nullable=False, server_default="sufficient"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_transcript_analyses_import_id", "transcript_analyses", ["import_id"])
    op.create_index("ix_transcript_analyses_owner_user_id", "transcript_analyses", ["owner_user_id"])
    op.create_index("ix_transcript_analyses_cache_key", "transcript_analyses", ["cache_key"])


def downgrade() -> None:
    op.drop_table("transcript_analyses")
    op.drop_table("transcript_scores")
    op.drop_table("transcript_imports")
