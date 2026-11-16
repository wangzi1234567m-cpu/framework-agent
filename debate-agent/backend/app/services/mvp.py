"""Transactional MVP commands; Agent candidates cannot write business state."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.skills import SkillRegistry
from app.models.p1 import (
    ApprovalRecord, CandidateRefMappingRecord, CaseRevisionRecord, CommandIdempotencyRecord,
    GenerationJobRecord, ProjectRecord, TopicAnalysisRecord, WorkingCopyArchiveRecord,
    WorkingCopyRecord, utcnow,
)
from app.schemas.agent import AgentContext, FrameworkRequest, FrameworkResponse, TopicRequest, TopicResponse
from app.schemas.api import (
    CreateProject, CreateRevision, DecideTopic, JobAccepted, JobView, ProjectView,
    ReviseTopic, SaveWorkingCopy, StartFramework, StartGeneration,
)
from app.schemas.domain import ArchivedWorkingCopy, CaseRevision, DebateCase, TopicAnalysis, TopicAnalysisContent, WorkingCopy
from app.services.candidate_materialization import materialize_framework


class BusinessError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def topic_view(row: TopicAnalysisRecord) -> TopicAnalysis:
    return TopicAnalysis(
        id=row.id, project_id=row.project_id, version=row.version,
        content=TopicAnalysisContent.model_validate(row.content), status=row.status,
    )


def working_view(row: WorkingCopyRecord) -> WorkingCopy:
    return WorkingCopy(
        id=row.id, project_id=row.project_id, edit_version=row.edit_version,
        approved_topic_analysis_id=row.approved_topic_analysis_id,
        case=DebateCase.model_validate(row.snapshot), updated_at=aware(row.updated_at),
    )


def archive_view(row: WorkingCopyArchiveRecord) -> ArchivedWorkingCopy:
    return ArchivedWorkingCopy(
        id=row.id, project_id=row.project_id, original_working_copy_id=row.original_working_copy_id,
        edit_version=row.edit_version, approved_topic_analysis_id=row.approved_topic_analysis_id,
        case=DebateCase.model_validate(row.snapshot), archived_at=aware(row.archived_at),
    )


def revision_view(row: CaseRevisionRecord) -> CaseRevision:
    return CaseRevision(
        id=row.id, project_id=row.project_id, revision_number=row.revision_number,
        source_edit_version=row.source_edit_version, approved_topic_analysis_id=row.approved_topic_analysis_id,
        snapshot=DebateCase.model_validate(row.snapshot), approved_by=row.approved_by,
        approved_at=aware(row.approved_at),
    )


class MVPService:
    def __init__(self, session: Session, skills: SkillRegistry, *, allow_draft: bool = False):
        self.session = session
        self.skills = skills
        self.allow_draft = allow_draft

    def _model_version(self) -> str:
        model = os.getenv("LLM_MODEL")
        if not model and not self.allow_draft:
            raise BusinessError("LLM_NOT_CONFIGURED", 503)
        return model or "mock-v1"

    def _project(self, project_id: UUID, actor: UUID, *, lock: bool = False) -> ProjectRecord:
        query = select(ProjectRecord).where(ProjectRecord.id == project_id, ProjectRecord.owner_id == actor)
        row = self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise BusinessError("PROJECT_NOT_FOUND", 404)
        return row

    def _job(self, job_id: UUID, actor: UUID) -> GenerationJobRecord:
        row = self.session.get(GenerationJobRecord, job_id)
        if row is None:
            raise BusinessError("JOB_NOT_FOUND", 404)
        self._project(row.project_id, actor)
        return row

    def create_project(self, actor: UUID, command: CreateProject) -> ProjectView:
        row = ProjectRecord(
            id=uuid4(), owner_id=actor, motion=command.motion, side=command.side,
            format=command.format, duration_seconds=command.duration_seconds,
            competition_context=command.competition_context, user_requirements=command.user_requirements,
            current_topic_version=0, created_at=utcnow(), updated_at=utcnow(),
        )
        self.session.add(row)
        self.session.flush()
        return self._project_view(row)

    @staticmethod
    def _project_view(row: ProjectRecord) -> ProjectView:
        return ProjectView(
            id=row.id, motion=row.motion, side=row.side, format=row.format,
            duration_seconds=row.duration_seconds, competition_context=row.competition_context,
            user_requirements=row.user_requirements, current_approved_topic_id=row.current_approved_topic_id,
            created_at=aware(row.created_at), updated_at=aware(row.updated_at),
        )

    def get_project(self, actor: UUID, project_id: UUID) -> ProjectView:
        return self._project_view(self._project(project_id, actor))

    def _enqueue(self, actor: UUID, project_id: UUID, job_type: str, key: str,
                 request: TopicRequest | FrameworkRequest, skill_hash: str, prompt_version: str,
                 expected_topic_version: int, command_digest: str) -> JobAccepted:
        snapshot = {
            "request": request.model_dump(mode="json"),
            "skill_hash": skill_hash,
            "expected_topic_version": expected_topic_version,
            "model_version": self._model_version(),
            "prompt_version": prompt_version,
            "command_digest": command_digest,
        }
        fingerprint = digest(snapshot)
        previous = self.session.scalar(select(GenerationJobRecord).where(
            GenerationJobRecord.actor_id == actor, GenerationJobRecord.project_id == project_id,
            GenerationJobRecord.job_type == job_type, GenerationJobRecord.idempotency_key == key,
        ))
        if previous:
            if previous.input_digest != fingerprint:
                raise BusinessError("IDEMPOTENCY_CONFLICT")
            return JobAccepted(job_id=previous.id)
        row = GenerationJobRecord(
            id=uuid4(), actor_id=actor, project_id=project_id, job_type=job_type, status="QUEUED",
            current_step="QUEUED", input_snapshot=snapshot, input_digest=fingerprint,
            attempt=0, max_attempts=3, idempotency_key=key,
            skill_version=request.context.skill_version, rule_set_version=request.context.rule_set_version,
            prompt_version=prompt_version, model_version=self._model_version(),
            created_at=utcnow(), updated_at=utcnow(),
        )
        self.session.add(row)
        self.session.flush()
        return JobAccepted(job_id=row.id)

    def start_topic(self, actor: UUID, project_id: UUID, command: StartGeneration) -> JobAccepted:
        project = self._project(project_id, actor, lock=True)
        fingerprint = digest(command.model_dump(mode="json"))
        previous = self._previous_job(actor, project.id, "TOPIC", command.idempotency_key)
        if previous:
            if previous.input_snapshot["command_digest"] != fingerprint:
                raise BusinessError("IDEMPOTENCY_CONFLICT")
            return JobAccepted(job_id=previous.id)
        if command.expected_topic_version is not None and command.expected_topic_version != project.current_topic_version:
            raise BusinessError("TOPIC_VERSION_CONFLICT")
        pack = self.skills.selected("TOPIC", allow_draft=self.allow_draft)
        request = TopicRequest(
            context=AgentContext(
                project_id=project.id, rule_set_version=pack.manifest.rule_set_version,
                skill_version=pack.manifest.skill_version, request_id=uuid4(),
            ),
            motion=project.motion, side=project.side, format=project.format,
            duration_seconds=project.duration_seconds, competition_context=project.competition_context,
            user_requirements=project.user_requirements,
        )
        return self._enqueue(actor, project.id, "TOPIC", command.idempotency_key, request,
                             pack.sha256, pack.manifest.prompt_version, project.current_topic_version, fingerprint)

    def _previous_job(self, actor: UUID, project_id: UUID, job_type: str, key: str) -> GenerationJobRecord | None:
        return self.session.scalar(select(GenerationJobRecord).where(
            GenerationJobRecord.actor_id == actor, GenerationJobRecord.project_id == project_id,
            GenerationJobRecord.job_type == job_type, GenerationJobRecord.idempotency_key == key,
        ))

    def get_topic(self, actor: UUID, topic_id: UUID) -> TopicAnalysis:
        row = self.session.get(TopicAnalysisRecord, topic_id)
        if row is None:
            raise BusinessError("TOPIC_NOT_FOUND", 404)
        self._project(row.project_id, actor)
        return topic_view(row)

    def current_topic(self, actor: UUID, project_id: UUID) -> TopicAnalysis:
        project = self._project(project_id, actor)
        row = self.session.scalar(select(TopicAnalysisRecord).where(
            TopicAnalysisRecord.project_id == project.id,
            TopicAnalysisRecord.version == project.current_topic_version,
        ))
        if row is None:
            raise BusinessError("TOPIC_NOT_FOUND", 404)
        return topic_view(row)

    def _command_previous(self, actor: UUID, project_id: UUID, operation: str, key: str,
                          fingerprint: str) -> UUID | None:
        previous = self.session.scalar(select(CommandIdempotencyRecord).where(
            CommandIdempotencyRecord.actor_id == actor, CommandIdempotencyRecord.project_id == project_id,
            CommandIdempotencyRecord.operation == operation, CommandIdempotencyRecord.key == key,
        ))
        if previous and previous.input_digest != fingerprint:
            raise BusinessError("IDEMPOTENCY_CONFLICT")
        return previous.resource_id if previous else None

    def _record_command(self, actor: UUID, project_id: UUID, operation: str, key: str,
                        fingerprint: str, resource_id: UUID) -> None:
        self.session.add(CommandIdempotencyRecord(
            id=uuid4(), actor_id=actor, project_id=project_id, operation=operation,
            key=key, input_digest=fingerprint, resource_id=resource_id,
        ))

    def revise_topic(self, actor: UUID, topic_id: UUID, command: ReviseTopic) -> TopicAnalysis:
        current = self.session.get(TopicAnalysisRecord, topic_id)
        if current is None:
            raise BusinessError("TOPIC_NOT_FOUND", 404)
        project = self._project(current.project_id, actor, lock=True)
        fingerprint = digest(command.model_dump(mode="json"))
        previous_id = self._command_previous(actor, project.id, "REVISE_TOPIC", command.idempotency_key, fingerprint)
        if previous_id:
            return topic_view(self.session.get(TopicAnalysisRecord, previous_id))
        if current.version != project.current_topic_version or command.expected_version != current.version:
            raise BusinessError("TOPIC_VERSION_CONFLICT")
        row = TopicAnalysisRecord(
            id=uuid4(), project_id=project.id, version=current.version + 1,
            content=command.content.model_dump(mode="json"), status="PENDING_APPROVAL", created_at=utcnow(),
        )
        project.current_topic_version = row.version
        project.current_approved_topic_id = None
        project.updated_at = utcnow()
        self.session.add(row)
        self._record_command(actor, project.id, "REVISE_TOPIC", command.idempotency_key, fingerprint, row.id)
        self.session.flush()
        return topic_view(row)

    def decide_topic(self, actor: UUID, topic_id: UUID, command: DecideTopic) -> TopicAnalysis:
        row = self.session.get(TopicAnalysisRecord, topic_id)
        if row is None:
            raise BusinessError("TOPIC_NOT_FOUND", 404)
        project = self._project(row.project_id, actor, lock=True)
        self.session.refresh(row)
        if row.version != project.current_topic_version or command.expected_version != row.version:
            raise BusinessError("TOPIC_VERSION_CONFLICT")
        if row.status != "PENDING_APPROVAL":
            raise BusinessError("TOPIC_NOT_PENDING")
        row.status = command.decision
        project.current_approved_topic_id = row.id if command.decision == "APPROVED" else None
        project.updated_at = utcnow()
        self.session.add(ApprovalRecord(
            id=uuid4(), project_id=project.id, target_type="TOPIC_ANALYSIS",
            target_id=row.id, target_version=row.version, decision=command.decision,
            reviewer_id=actor, comment=command.comment, created_at=utcnow(),
        ))
        self.session.flush()
        return topic_view(row)

    def start_framework(self, actor: UUID, project_id: UUID, command: StartFramework) -> JobAccepted:
        project = self._project(project_id, actor, lock=True)
        fingerprint = digest(command.model_dump(mode="json"))
        previous = self._previous_job(actor, project.id, "FRAMEWORK", command.idempotency_key)
        if previous:
            if previous.input_snapshot["command_digest"] != fingerprint:
                raise BusinessError("IDEMPOTENCY_CONFLICT")
            return JobAccepted(job_id=previous.id)
        if project.current_approved_topic_id != command.approved_topic_analysis_id:
            raise BusinessError("TOPIC_NOT_APPROVED")
        topic = self.session.get(TopicAnalysisRecord, command.approved_topic_analysis_id)
        if topic is None or topic.version != command.expected_topic_version or topic.status != "APPROVED":
            raise BusinessError("TOPIC_VERSION_CONFLICT")
        working = self.session.scalar(select(WorkingCopyRecord).where(WorkingCopyRecord.project_id == project.id))
        pack = self.skills.selected("FRAMEWORK", allow_draft=self.allow_draft)
        request = FrameworkRequest(
            context=AgentContext(
                project_id=project.id, rule_set_version=pack.manifest.rule_set_version,
                skill_version=pack.manifest.skill_version, request_id=uuid4(),
            ),
            motion=project.motion, side=project.side, format=project.format,
            duration_seconds=project.duration_seconds, competition_context=project.competition_context,
            user_requirements=project.user_requirements, approved_topic_analysis_id=topic.id,
            topic_version=topic.version, approved_topic=TopicAnalysisContent.model_validate(topic.content),
            base_edit_version=working.edit_version if working else None,
        )
        return self._enqueue(actor, project.id, "FRAMEWORK", command.idempotency_key, request,
                             pack.sha256, pack.manifest.prompt_version, topic.version, fingerprint)

    def _leased_job(self, job_id: UUID, worker_id: str, attempt: int) -> GenerationJobRecord:
        job = self.session.scalar(select(GenerationJobRecord).where(
            GenerationJobRecord.id == job_id,
        ).with_for_update())
        if job is None or job.status != "RUNNING" or job.lease_owner != worker_id or job.attempt != attempt:
            raise BusinessError("JOB_LEASE_LOST")
        if job.lease_until is None or aware(job.lease_until) <= utcnow():
            raise BusinessError("JOB_LEASE_LOST")
        return job

    def accept_topic(self, job_id: UUID, worker_id: str, attempt: int, response: TopicResponse) -> UUID:
        job = self._leased_job(job_id, worker_id, attempt)
        if job.job_type != "TOPIC":
            raise BusinessError("JOB_TYPE_MISMATCH")
        project = self._project(job.project_id, job.actor_id, lock=True)
        if project.current_topic_version != job.input_snapshot["expected_topic_version"]:
            raise BusinessError("STALE_TOPIC_RESULT")
        row = TopicAnalysisRecord(
            id=uuid4(), project_id=project.id, version=project.current_topic_version + 1,
            content=response.analysis.model_dump(mode="json"), status="PENDING_APPROVAL", created_at=utcnow(),
        )
        project.current_topic_version = row.version
        project.current_approved_topic_id = None
        project.updated_at = utcnow()
        self.session.add(row)
        job.output_snapshot = {"topic_analysis_id": str(row.id), "uncertainty_notes": response.uncertainty_notes}
        self._succeed(job)
        self.session.flush()
        return row.id

    def accept_framework(self, job_id: UUID, worker_id: str, attempt: int,
                         response: FrameworkResponse) -> UUID:
        job = self._leased_job(job_id, worker_id, attempt)
        if job.job_type != "FRAMEWORK":
            raise BusinessError("JOB_TYPE_MISMATCH")
        request = FrameworkRequest.model_validate(job.input_snapshot["request"])
        project = self._project(job.project_id, job.actor_id, lock=True)
        if project.current_approved_topic_id != request.approved_topic_analysis_id:
            raise BusinessError("STALE_TOPIC_RESULT")
        topic = self.session.get(TopicAnalysisRecord, request.approved_topic_analysis_id)
        if topic is None or topic.version != request.topic_version or topic.status != "APPROVED":
            raise BusinessError("STALE_TOPIC_RESULT")
        working = self.session.scalar(select(WorkingCopyRecord).where(
            WorkingCopyRecord.project_id == project.id,
        ).with_for_update())
        if (working.edit_version if working else None) != request.base_edit_version:
            raise BusinessError("STALE_WORKING_COPY")
        case, mapping = materialize_framework(request, response, job.id)
        if working is None:
            working = WorkingCopyRecord(
                id=uuid4(), project_id=project.id, approved_topic_analysis_id=topic.id,
                edit_version=1, snapshot=case.model_dump(mode="json"), updated_at=utcnow(),
            )
            self.session.add(working)
        else:
            if working.approved_topic_analysis_id != topic.id:
                self.session.add(WorkingCopyArchiveRecord(
                    id=uuid4(), project_id=project.id, original_working_copy_id=working.id,
                    approved_topic_analysis_id=working.approved_topic_analysis_id,
                    edit_version=working.edit_version, snapshot=working.snapshot, archived_at=utcnow(),
                ))
                working.approved_topic_analysis_id = topic.id
            working.edit_version += 1
            working.snapshot = case.model_dump(mode="json")
            working.updated_at = utcnow()
        self.session.add(CandidateRefMappingRecord(
            job_id=job.id, request_id=mapping.request_id,
            candidate_ref_to_id={ref: str(value) for ref, value in mapping.candidate_ref_to_id.items()},
        ))
        job.output_snapshot = {"working_copy_id": str(working.id), "uncertainty_notes": response.uncertainty_notes}
        self._succeed(job)
        self.session.flush()
        return working.id

    @staticmethod
    def _succeed(job: GenerationJobRecord) -> None:
        job.status = "SUCCEEDED"
        job.current_step = "FINALIZE"
        job.lease_owner = None
        job.lease_until = None
        job.updated_at = utcnow()

    def get_working(self, actor: UUID, case_id: UUID) -> WorkingCopy:
        row = self.session.get(WorkingCopyRecord, case_id)
        if row is None:
            raise BusinessError("WORKING_COPY_NOT_FOUND", 404)
        self._project(row.project_id, actor)
        return working_view(row)

    def project_working(self, actor: UUID, project_id: UUID) -> WorkingCopy:
        self._project(project_id, actor)
        row = self.session.scalar(select(WorkingCopyRecord).where(WorkingCopyRecord.project_id == project_id))
        if row is None:
            raise BusinessError("WORKING_COPY_NOT_FOUND", 404)
        return working_view(row)

    def list_working_archives(self, actor: UUID, project_id: UUID,
                              limit: int = 100, offset: int = 0) -> list[ArchivedWorkingCopy]:
        self._project(project_id, actor)
        rows = self.session.scalars(select(WorkingCopyArchiveRecord).where(
            WorkingCopyArchiveRecord.project_id == project_id,
        ).order_by(WorkingCopyArchiveRecord.archived_at.desc(), WorkingCopyArchiveRecord.id)
            .offset(offset).limit(limit)).all()
        return [archive_view(row) for row in rows]

    def save_working(self, actor: UUID, case_id: UUID, command: SaveWorkingCopy) -> WorkingCopy:
        row = self.session.get(WorkingCopyRecord, case_id)
        if row is None:
            raise BusinessError("WORKING_COPY_NOT_FOUND", 404)
        project = self._project(row.project_id, actor, lock=True)
        self.session.refresh(row)
        if row.edit_version != command.expected_edit_version:
            raise BusinessError("EDIT_VERSION_CONFLICT")
        if project.current_approved_topic_id != row.approved_topic_analysis_id:
            raise BusinessError("STALE_WORKING_COPY")
        approved = self.session.get(TopicAnalysisRecord, row.approved_topic_analysis_id)
        if (command.case.motion, command.case.side) != (project.motion, project.side):
            raise BusinessError("CASE_TOPIC_MISMATCH")
        content = TopicAnalysisContent.model_validate(approved.content)
        if (command.case.definitions, command.case.judging_criteria) != (content.definitions, content.judging_criteria):
            raise BusinessError("APPROVED_TOPIC_IMMUTABLE")
        row.snapshot = command.case.model_dump(mode="json")
        row.edit_version += 1
        row.updated_at = utcnow()
        self.session.flush()
        return working_view(row)

    def create_revision(self, actor: UUID, case_id: UUID, command: CreateRevision) -> CaseRevision:
        working = self.session.get(WorkingCopyRecord, case_id)
        if working is None:
            raise BusinessError("WORKING_COPY_NOT_FOUND", 404)
        project = self._project(working.project_id, actor, lock=True)
        fingerprint = digest(command.model_dump(mode="json"))
        previous_id = self._command_previous(actor, project.id, "CREATE_REVISION", command.idempotency_key, fingerprint)
        if previous_id:
            return revision_view(self.session.get(CaseRevisionRecord, previous_id))
        self.session.refresh(working)
        if working.edit_version != command.expected_edit_version:
            raise BusinessError("EDIT_VERSION_CONFLICT")
        if project.current_approved_topic_id != working.approved_topic_analysis_id:
            raise BusinessError("STALE_WORKING_COPY")
        number = self.session.scalar(select(func.max(CaseRevisionRecord.revision_number)).where(
            CaseRevisionRecord.project_id == project.id,
        )) or 0
        row = CaseRevisionRecord(
            id=uuid4(), project_id=project.id, revision_number=number + 1,
            source_edit_version=working.edit_version, approved_topic_analysis_id=working.approved_topic_analysis_id,
            snapshot=working.snapshot, approved_by=actor, approved_at=utcnow(),
        )
        self.session.add(row)
        self._record_command(actor, project.id, "CREATE_REVISION", command.idempotency_key, fingerprint, row.id)
        self.session.flush()
        return revision_view(row)

    def get_revision(self, actor: UUID, revision_id: UUID) -> CaseRevision:
        row = self.session.get(CaseRevisionRecord, revision_id)
        if row is None:
            raise BusinessError("REVISION_NOT_FOUND", 404)
        self._project(row.project_id, actor)
        return revision_view(row)

    def get_job(self, actor: UUID, job_id: UUID) -> JobView:
        row = self._job(job_id, actor)
        return JobView(
            id=row.id, project_id=row.project_id, job_type=row.job_type,
            status=row.status, current_step=row.current_step, attempt=row.attempt, error_code=row.error_code,
            created_at=aware(row.created_at), updated_at=aware(row.updated_at),
        )
