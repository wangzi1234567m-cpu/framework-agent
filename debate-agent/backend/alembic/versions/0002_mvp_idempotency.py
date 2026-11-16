"""Record idempotent synchronous commands.

Revision ID: 0002_mvp
Revises: 0001_p1
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_mvp"
down_revision = "0001_p1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "command_idempotency",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.UniqueConstraint("actor_id", "project_id", "operation", "key", name="uq_command_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("command_idempotency")
