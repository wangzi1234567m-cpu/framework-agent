"""P1 persistence schema; Agent candidate DTOs never import these models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


document_type = JSON().with_variant(JSONB, "postgresql")


class ProjectRecord(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("duration_seconds > 0", name="ck_projects_duration"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    motion: Mapped[str] = mapped_column(String(500), nullable=False)
    side: Mapped[str] = mapped_column(String(100), nullable=False)
    format: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(nullable=False)
    competition_context: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    user_requirements: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    current_topic_version: Mapped[int] = mapped_column(default=0, nullable=False)
    current_approved_topic_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("topic_analyses.id", use_alter=True, name="fk_projects_current_topic"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TopicAnalysisRecord(Base):
    __tablename__ = "topic_analyses"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_topic_project_version"),
        CheckConstraint("version > 0", name="ck_topic_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(document_type, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkingCopyRecord(Base):
    __tablename__ = "working_copies"
    __table_args__ = (
        CheckConstraint("edit_version > 0", name="ck_working_copy_version"),
        UniqueConstraint("project_id", name="uq_working_copy_project"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    approved_topic_analysis_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("topic_analyses.id"), nullable=False)
    edit_version: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(document_type, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkingCopyArchiveRecord(Base):
    __tablename__ = "working_copy_archives"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    original_working_copy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    approved_topic_analysis_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("topic_analyses.id"), nullable=False)
    edit_version: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(document_type, nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseRevisionRecord(Base):
    __tablename__ = "case_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision_number", name="uq_revision_project_number"),
        CheckConstraint("revision_number > 0", name="ck_revision_number"),
        CheckConstraint("source_edit_version > 0", name="ck_revision_edit_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(nullable=False)
    source_edit_version: Mapped[int] = mapped_column(nullable=False)
    approved_topic_analysis_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("topic_analyses.id"), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(document_type, nullable=False)
    approved_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApprovalRecord(Base):
    __tablename__ = "approvals"
    __table_args__ = (CheckConstraint("target_version > 0", name="ck_approval_target_version"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    target_version: Mapped[int] = mapped_column(nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    comment: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationJobRecord(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        UniqueConstraint("actor_id", "project_id", "job_type", "idempotency_key", name="uq_job_idempotency"),
        CheckConstraint("attempt >= 0", name="ck_job_attempt"),
        CheckConstraint("max_attempts > 0", name="ck_job_max_attempts"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_step: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(document_type, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(document_type)
    attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    model_version: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(128))
    rule_set_version: Mapped[str | None] = mapped_column(String(128))
    skill_version: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CandidateRefMappingRecord(Base):
    __tablename__ = "candidate_ref_mappings"

    job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("generation_jobs.id"), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    candidate_ref_to_id: Mapped[dict[str, str]] = mapped_column(document_type, nullable=False)


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency"
    __table_args__ = (
        UniqueConstraint("actor_id", "project_id", "operation", "key", name="uq_command_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
