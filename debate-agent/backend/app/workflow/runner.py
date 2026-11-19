"""Short-transaction durable runner; model calls never hold database locks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.runtime import AgentFailure, FrameworkBuilder, ModelPort, TopicAnalyzer
from app.agents.skills import SkillError, SkillRegistry
from app.core.database import session_scope
from app.models.p1 import GenerationJobRecord, utcnow
from app.schemas.agent import FrameworkRequest, TopicRequest
from app.services.mvp import BusinessError, MVPService, aware


class JobRunner:
    def __init__(
        self, sessions: sessionmaker[Session], skills: SkillRegistry,
        model_factory: Callable[[str], ModelPort], worker_id: str, *,
        lease_seconds: int = 240, allow_draft: bool = False,
    ):
        self.sessions = sessions
        self.skills = skills
        self.model_factory = model_factory
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.allow_draft = allow_draft

    def claim_next(self) -> tuple[UUID, int, dict] | None:
        with session_scope(self.sessions) as session:
            now = utcnow()
            row = session.scalar(
                select(GenerationJobRecord).where(or_(
                    GenerationJobRecord.status == "QUEUED",
                    (GenerationJobRecord.status == "RUNNING") & (GenerationJobRecord.lease_until < now),
                )).order_by(GenerationJobRecord.created_at, GenerationJobRecord.id)
                .with_for_update(skip_locked=True).limit(1)
            )
            if row is None:
                return None
            if row.attempt >= row.max_attempts:
                row.status = "FAILED"
                row.error_code = "MAX_ATTEMPTS"
                row.lease_owner = None
                row.lease_until = None
                row.updated_at = now
                return None
            row.attempt += 1
            row.status = "RUNNING"
            row.current_step = "ANALYZE_INPUT"
            row.lease_owner = self.worker_id
            row.lease_until = now + timedelta(seconds=self.lease_seconds)
            row.updated_at = now
            session.flush()
            return row.id, row.attempt, row.input_snapshot

    def _update_step(self, job_id: UUID, attempt: int, step: str) -> None:
        with session_scope(self.sessions) as session:
            service = MVPService(session, self.skills, allow_draft=self.allow_draft)
            job = service._leased_job(job_id, self.worker_id, attempt)
            job.current_step = step
            job.lease_until = utcnow() + timedelta(seconds=self.lease_seconds)
            job.updated_at = utcnow()

    def _fail(self, job_id: UUID, attempt: int, code: str) -> None:
        with session_scope(self.sessions) as session:
            row = session.scalar(
                select(GenerationJobRecord).where(GenerationJobRecord.id == job_id).with_for_update(),
            )
            if row is None or row.status != "RUNNING" or row.lease_owner != self.worker_id or row.attempt != attempt:
                return
            if row.lease_until is None or aware(row.lease_until) <= utcnow():
                return
            retry = code in {"LLM_TIMEOUT", "LLM_TRANSIENT"} and row.attempt < row.max_attempts
            row.status = "QUEUED" if retry else "FAILED"
            row.error_code = code
            row.lease_owner = None
            row.lease_until = None
            row.updated_at = utcnow()

    async def run_once(self) -> bool:
        claim = self.claim_next()
        if claim is None:
            return False
        job_id, attempt, snapshot = claim
        try:
            request_data = snapshot["request"]
            kind = "TOPIC" if "approved_topic_analysis_id" not in request_data else "FRAMEWORK"
            skill = self.skills.load(kind, request_data["context"]["skill_version"], allow_draft=self.allow_draft)
            if skill.sha256 != snapshot["skill_hash"]:
                raise AgentFailure("SKILL_HASH_MISMATCH")
            model = self.model_factory(kind)
            if getattr(model, "model", snapshot["model_version"]) != snapshot["model_version"]:
                raise AgentFailure("MODEL_VERSION_MISMATCH")

            async def checkpoint(step: str, _payload: dict) -> None:
                self._update_step(job_id, attempt, step)

            if kind == "TOPIC":
                result = await TopicAnalyzer(skill, model).run(TopicRequest.model_validate(request_data), checkpoint)
                with session_scope(self.sessions) as session:
                    MVPService(session, self.skills, allow_draft=self.allow_draft).accept_topic(
                        job_id, self.worker_id, attempt, result,
                    )
            else:
                result = await FrameworkBuilder(skill, model).run(
                    FrameworkRequest.model_validate(request_data), checkpoint,
                )
                with session_scope(self.sessions) as session:
                    MVPService(session, self.skills, allow_draft=self.allow_draft).accept_framework(
                        job_id, self.worker_id, attempt, result,
                    )
        except (BusinessError, AgentFailure, SkillError) as exc:
            self._fail(job_id, attempt, exc.code if hasattr(exc, "code") else "SKILL_INVALID")
        except Exception:
            self._fail(job_id, attempt, "WORKER_ERROR")
            raise
        return True
