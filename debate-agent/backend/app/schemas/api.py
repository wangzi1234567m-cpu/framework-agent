"""Selected HTTP command DTOs; authenticated actor comes from the server context."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from .domain import Contract, DebateCase, JobStatus, TopicAnalysisContent


class CreateProject(Contract):
    motion: str = Field(min_length=1)
    side: str = Field(min_length=1)
    format: str
    duration_seconds: int = Field(gt=0)
    competition_context: str = ""
    user_requirements: str = ""


class StartGeneration(Contract):
    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_topic_version: int | None = Field(default=None, ge=1)


class StartFramework(Contract):
    idempotency_key: str = Field(min_length=1, max_length=128)
    approved_topic_analysis_id: UUID
    expected_topic_version: int = Field(ge=1)


class ProjectView(Contract):
    id: UUID
    motion: str
    side: str
    format: str
    duration_seconds: int
    competition_context: str = ""
    user_requirements: str = ""
    current_approved_topic_id: UUID | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class JobView(Contract):
    id: UUID
    project_id: UUID
    job_type: str
    status: JobStatus
    current_step: str
    attempt: int = Field(ge=0)
    error_code: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DecideTopic(Contract):
    expected_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED"]
    comment: str = ""


class ReviseTopic(Contract):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    content: TopicAnalysisContent


class DecideEvidence(Contract):
    expected_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED", "NEEDS_MORE_SOURCE"]
    comment: str = ""


class SaveWorkingCopy(Contract):
    expected_edit_version: int = Field(ge=1)
    case: DebateCase


class CreateRevision(Contract):
    expected_edit_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class DecideProposal(Contract):
    expected_edit_version: int = Field(ge=1)
    decision: Literal["ACCEPTED", "REJECTED"]


class JobAccepted(Contract):
    job_id: UUID
    status: Literal["QUEUED"] = "QUEUED"


class ErrorResponse(Contract):
    error_code: str
    message: str
    request_id: UUID
