"""Preserve unsaved working copy state when a new approved topic replaces it.

Revision ID: 0003_archives
Revises: 0002_mvp
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_archives"
down_revision = "0002_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "working_copy_archives",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("original_working_copy_id", sa.Uuid(), nullable=False),
        sa.Column("approved_topic_analysis_id", sa.Uuid(), sa.ForeignKey("topic_analyses.id"), nullable=False),
        sa.Column("edit_version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_working_copy_archives_project_id", "working_copy_archives", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_working_copy_archives_project_id", table_name="working_copy_archives")
    op.drop_table("working_copy_archives")
