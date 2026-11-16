"""P1 projects, versioned topic, working copy, revision and durable jobs.

Revision ID: 0001_p1
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_p1"
down_revision = None
branch_labels = None
depends_on = None

uid = sa.Uuid()
ts = sa.DateTime(timezone=True)
doc = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", uid, primary_key=True),
        sa.Column("owner_id", uid, nullable=False),
        sa.Column("motion", sa.String(500), nullable=False),
        sa.Column("side", sa.String(100), nullable=False),
        sa.Column("format", sa.String(100), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("competition_context", sa.String(2000), nullable=False),
        sa.Column("user_requirements", sa.String(2000), nullable=False),
        sa.Column("current_topic_version", sa.Integer(), nullable=False),
        sa.Column("current_approved_topic_id", uid),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("updated_at", ts, nullable=False),
        sa.CheckConstraint("duration_seconds > 0", name="ck_projects_duration"),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_table(
        "topic_analyses",
        sa.Column("id", uid, primary_key=True),
        sa.Column("project_id", uid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", doc, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", ts, nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_topic_project_version"),
        sa.CheckConstraint("version > 0", name="ck_topic_version"),
    )
    op.create_index("ix_topic_analyses_project_id", "topic_analyses", ["project_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_projects_current_topic", "projects", "topic_analyses",
            ["current_approved_topic_id"], ["id"],
        )
    op.create_table(
        "working_copies",
        sa.Column("id", uid, primary_key=True),
        sa.Column("project_id", uid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("approved_topic_analysis_id", uid, sa.ForeignKey("topic_analyses.id"), nullable=False),
        sa.Column("edit_version", sa.Integer(), nullable=False),
        sa.Column("snapshot", doc, nullable=False),
        sa.Column("updated_at", ts, nullable=False),
        sa.UniqueConstraint("project_id", name="uq_working_copy_project"),
        sa.CheckConstraint("edit_version > 0", name="ck_working_copy_version"),
    )
    op.create_table(
        "case_revisions",
        sa.Column("id", uid, primary_key=True),
        sa.Column("project_id", uid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("source_edit_version", sa.Integer(), nullable=False),
        sa.Column("approved_topic_analysis_id", uid, sa.ForeignKey("topic_analyses.id"), nullable=False),
        sa.Column("snapshot", doc, nullable=False),
        sa.Column("approved_by", uid, nullable=False),
        sa.Column("approved_at", ts, nullable=False),
        sa.UniqueConstraint("project_id", "revision_number", name="uq_revision_project_number"),
        sa.CheckConstraint("revision_number > 0", name="ck_revision_number"),
        sa.CheckConstraint("source_edit_version > 0", name="ck_revision_edit_version"),
    )
    op.create_index("ix_case_revisions_project_id", "case_revisions", ["project_id"])
    op.create_table(
        "approvals",
        sa.Column("id", uid, primary_key=True),
        sa.Column("project_id", uid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", uid, nullable=False),
        sa.Column("target_version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reviewer_id", uid, nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("created_at", ts, nullable=False),
        sa.CheckConstraint("target_version > 0", name="ck_approval_target_version"),
    )
    op.create_index("ix_approvals_project_id", "approvals", ["project_id"])
    op.create_table(
        "generation_jobs",
        sa.Column("id", uid, primary_key=True),
        sa.Column("project_id", uid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("actor_id", uid, nullable=False),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_step", sa.String(64), nullable=False),
        sa.Column("input_snapshot", doc, nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("output_snapshot", doc),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("lease_owner", sa.String(100)),
        sa.Column("lease_until", ts),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.String(2000)),
        sa.Column("model_version", sa.String(128)),
        sa.Column("prompt_version", sa.String(128)),
        sa.Column("rule_set_version", sa.String(128)),
        sa.Column("skill_version", sa.String(128)),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("updated_at", ts, nullable=False),
        sa.UniqueConstraint("actor_id", "project_id", "job_type", "idempotency_key", name="uq_job_idempotency"),
        sa.CheckConstraint("attempt >= 0", name="ck_job_attempt"),
        sa.CheckConstraint("max_attempts > 0", name="ck_job_max_attempts"),
    )
    op.create_index("ix_generation_jobs_project_id", "generation_jobs", ["project_id"])
    op.create_table(
        "candidate_ref_mappings",
        sa.Column("job_id", uid, sa.ForeignKey("generation_jobs.id"), primary_key=True),
        sa.Column("request_id", uid, nullable=False),
        sa.Column("candidate_ref_to_id", doc, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("candidate_ref_mappings")
    op.drop_index("ix_generation_jobs_project_id", table_name="generation_jobs")
    op.drop_table("generation_jobs")
    op.drop_index("ix_approvals_project_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_case_revisions_project_id", table_name="case_revisions")
    op.drop_table("case_revisions")
    op.drop_table("working_copies")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_projects_current_topic", "projects", type_="foreignkey")
    op.drop_index("ix_topic_analyses_project_id", table_name="topic_analyses")
    op.drop_table("topic_analyses")
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_table("projects")
