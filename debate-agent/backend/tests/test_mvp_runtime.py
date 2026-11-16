import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.runtime import AgentFailure, FrameworkBuilder, TopicAnalyzer
from app.agents.skills import SkillError, SkillRegistry
from app.api.p1 import get_service, require_actor
from app.core.database import session_scope
from app.main import app
from app.models.p1 import CandidateRefMappingRecord, GenerationJobRecord, utcnow
from app.schemas.agent import FrameworkRequest, TopicRequest, TopicResponse
from app.schemas.api import CreateProject, CreateRevision, DecideTopic, ReviseTopic, SaveWorkingCopy, StartFramework, StartGeneration
from app.services.export import render_revision_markdown
from app.services.mvp import BusinessError, MVPService
from app.workflow.runner import JobRunner

BACKEND = Path(__file__).resolve().parents[1]
SKILLS = SkillRegistry(BACKEND / "knowledge" / "skills")
EXAMPLES = json.loads(Path(__file__).with_name("p1_contract_examples.json").read_text(encoding="utf-8"))


class ScriptedModel:
    model = "mock-v1"

    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = []
        self.review_findings = []

    async def complete(self, stage, instructions, payload):
        self.calls.append(stage)
        if stage == "analyze":
            return {"summary": "synthetic example"}
        if stage == "review":
            if self.review_findings:
                return {"findings": self.review_findings.pop(0)}
            return {"findings": []}
        return copy.deepcopy(self.candidate)


class AgentSkeletonTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def request(name, skill):
        value = copy.deepcopy(EXAMPLES[name])
        value["context"]["skill_version"] = skill.manifest.skill_version
        value["context"]["rule_set_version"] = skill.manifest.rule_set_version
        return value

    async def test_drafts_load_only_when_explicitly_allowed_and_stages_execute(self):
        with self.assertRaises(SkillError):
            SKILLS.load("TOPIC", "0.1.0")
        topic_skill = SKILLS.load("TOPIC", "0.1.0", allow_draft=True)
        framework_skill = SKILLS.load("FRAMEWORK", "0.1.0", allow_draft=True)
        topic_model = ScriptedModel(EXAMPLES["topic_response"])
        topic_model.review_findings = [[{
            "target": "analysis", "rule_id": "TEST", "severity": "IMPROVEMENT",
            "issue": "needs clarity", "suggested_fix": "clarify",
        }]]
        topic = await TopicAnalyzer(topic_skill, topic_model).run(
            TopicRequest.model_validate(self.request("topic_request", topic_skill)),
        )
        self.assertEqual(topic_model.calls, ["analyze", "draft", "review", "revise", "review"])
        self.assertEqual(topic.analysis.discussion_scope, EXAMPLES["topic_response"]["analysis"]["discussion_scope"])
        framework_model = ScriptedModel(EXAMPLES["framework_response"])
        framework = await FrameworkBuilder(framework_skill, framework_model).run(
            FrameworkRequest.model_validate(self.request("framework_request", framework_skill)),
        )
        self.assertEqual(framework.arguments[0].ref, "arg-1")
        self.assertEqual(framework_model.calls, ["analyze", "draft", "review"])

    async def test_self_review_cannot_approve_blocking_error(self):
        model = ScriptedModel(EXAMPLES["topic_response"])
        finding = {
            "target": "analysis", "rule_id": "TEST", "severity": "BLOCKING",
            "issue": "invalid", "suggested_fix": "fix",
        }
        model.review_findings = [[finding], [finding]]
        skill = SKILLS.load("TOPIC", "0.1.0", allow_draft=True)
        with self.assertRaisesRegex(AgentFailure, "SELF_REVIEW_BLOCKED"):
            await TopicAnalyzer(skill, model).run(
                TopicRequest.model_validate(self.request("topic_request", skill)),
            )
        self.assertEqual(model.calls.count("revise"), 1)


class MVPPersistenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        url = f"sqlite+pysqlite:///{(Path(self.temp.name) / 'mvp.sqlite').as_posix()}"
        with patch.dict(os.environ, {"DATABASE_URL": url}):
            command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
        self.engine = create_engine(url)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.actor = uuid4()
        self.other_actor = uuid4()
        self.models = {
            "TOPIC": ScriptedModel(EXAMPLES["topic_response"]),
            "FRAMEWORK": ScriptedModel(EXAMPLES["framework_response"]),
        }
        self.runner = JobRunner(self.sessions, SKILLS, lambda kind: self.models[kind], "test-worker", allow_draft=True)

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def service(self):
        return session_scope(self.sessions)

    def create_project(self):
        with self.service() as session:
            return MVPService(session, SKILLS, allow_draft=True).create_project(
                self.actor, CreateProject(motion="压力有利还是有害", side="反",
                                          format="4v4", duration_seconds=240),
            ).id

    async def test_full_mvp_flow_and_idempotency(self):
        project = self.create_project()
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            with self.assertRaisesRegex(BusinessError, "TOPIC_NOT_APPROVED"):
                service.start_framework(self.actor, project, StartFramework(
                    idempotency_key="not-yet", approved_topic_analysis_id=uuid4(), expected_topic_version=1,
                ))
            first = service.start_topic(self.actor, project, StartGeneration(idempotency_key="topic-1"))
            self.assertEqual(first.job_id, service.start_topic(
                self.actor, project, StartGeneration(idempotency_key="topic-1"),
            ).job_id)
        self.assertTrue(await self.runner.run_once())
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            self.assertEqual(service.get_job(self.actor, first.job_id).status, "SUCCEEDED")
            topic = service.current_topic(self.actor, project)
            self.assertEqual(topic.status, "PENDING_APPROVAL")
            self.assertEqual(first.job_id, service.start_topic(
                self.actor, project, StartGeneration(idempotency_key="topic-1"),
            ).job_id)
            with self.assertRaisesRegex(BusinessError, "IDEMPOTENCY_CONFLICT"):
                service.start_topic(self.actor, project, StartGeneration(
                    idempotency_key="topic-1", expected_topic_version=1,
                ))
            with self.assertRaisesRegex(BusinessError, "PROJECT_NOT_FOUND"):
                service.get_project(self.other_actor, project)
            approved = service.decide_topic(self.actor, topic.id, DecideTopic(expected_version=1, decision="APPROVED"))
            self.assertEqual(approved.status, "APPROVED")
            framework_job = service.start_framework(self.actor, project, StartFramework(
                idempotency_key="framework-1", approved_topic_analysis_id=topic.id, expected_topic_version=1,
            ))
        self.assertTrue(await self.runner.run_once())
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            self.assertEqual(service.get_job(self.actor, framework_job.job_id).status, "SUCCEEDED")
            self.assertEqual(framework_job.job_id, service.start_framework(
                self.actor, project, StartFramework(
                    idempotency_key="framework-1", approved_topic_analysis_id=topic.id, expected_topic_version=1,
                ),
            ).job_id)
            working = service.project_working(self.actor, project)
            self.assertEqual(working.case.definitions, topic.content.definitions)
            self.assertEqual(session.scalar(select(CandidateRefMappingRecord).where(
                CandidateRefMappingRecord.job_id == framework_job.job_id,
            )).candidate_ref_to_id["arg-1"], str(working.case.arguments[0].id))
            modified = working.case.model_copy(deep=True)
            modified.arguments[0].title = "人工修改过的论点"
            saved = service.save_working(self.actor, working.id, SaveWorkingCopy(
                expected_edit_version=1, case=modified,
            ))
            self.assertEqual(saved.edit_version, 2)
            revision = service.create_revision(self.actor, working.id, CreateRevision(
                expected_edit_version=2, idempotency_key="confirm-1",
            ))
            self.assertEqual(revision.snapshot.arguments[0].title, "人工修改过的论点")
            self.assertIn("待查证据（非已核验事实）", render_revision_markdown(revision))
            self.assertEqual(service.create_revision(self.actor, working.id, CreateRevision(
                expected_edit_version=2, idempotency_key="confirm-1",
            )).id, revision.id)
            with self.assertRaisesRegex(BusinessError, "EDIT_VERSION_CONFLICT"):
                service.save_working(self.actor, working.id, SaveWorkingCopy(
                    expected_edit_version=1, case=modified,
                ))

    async def test_topic_edit_rejects_stale_framework_job(self):
        project = self.create_project()
        with self.service() as session:
            job = MVPService(session, SKILLS, allow_draft=True).start_topic(
                self.actor, project, StartGeneration(idempotency_key="topic"),
            )
        await self.runner.run_once()
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            topic = service.current_topic(self.actor, project)
            service.decide_topic(self.actor, topic.id, DecideTopic(expected_version=1, decision="APPROVED"))
            service.start_framework(self.actor, project, StartFramework(
                idempotency_key="framework", approved_topic_analysis_id=topic.id, expected_topic_version=1,
            ))
            revised = service.revise_topic(self.actor, topic.id, ReviseTopic(
                expected_version=1, idempotency_key="edit-topic", content=topic.content,
            ))
            self.assertEqual(revised.version, 2)
            with self.assertRaisesRegex(BusinessError, "TOPIC_NOT_APPROVED"):
                service.start_framework(self.actor, project, StartFramework(
                    idempotency_key="new-framework", approved_topic_analysis_id=topic.id, expected_topic_version=1,
                ))
        await self.runner.run_once()
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            self.assertEqual(service.current_topic(self.actor, project).status, "PENDING_APPROVAL")
            with self.assertRaisesRegex(BusinessError, "WORKING_COPY_NOT_FOUND"):
                service.project_working(self.actor, project)
            failed = session.scalar(select(GenerationJobRecord).where(GenerationJobRecord.job_type == "FRAMEWORK"))
            self.assertEqual(failed.error_code, "STALE_TOPIC_RESULT")

    async def test_second_framework_job_cannot_overwrite_new_working_copy(self):
        project = self.create_project()
        with self.service() as session:
            MVPService(session, SKILLS, allow_draft=True).start_topic(
                self.actor, project, StartGeneration(idempotency_key="t"),
            )
        await self.runner.run_once()
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            topic = service.current_topic(self.actor, project)
            service.decide_topic(self.actor, topic.id, DecideTopic(expected_version=1, decision="APPROVED"))
            for key in ("f1", "f2"):
                service.start_framework(self.actor, project, StartFramework(
                    idempotency_key=key, approved_topic_analysis_id=topic.id, expected_topic_version=1,
                ))
        await self.runner.run_once()
        await self.runner.run_once()
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            self.assertEqual(service.project_working(self.actor, project).edit_version, 1)
            jobs = session.scalars(select(GenerationJobRecord).where(
                GenerationJobRecord.job_type == "FRAMEWORK",
            )).all()
            self.assertEqual({job.status for job in jobs}, {"SUCCEEDED", "FAILED"})
            self.assertEqual(next(job.error_code for job in jobs if job.status == "FAILED"), "STALE_WORKING_COPY")

    async def test_expired_worker_cannot_commit_after_another_claim(self):
        project = self.create_project()
        with self.service() as session:
            MVPService(session, SKILLS, allow_draft=True).start_topic(
                self.actor, project, StartGeneration(idempotency_key="lease"),
            )
        first_id, first_attempt, _ = self.runner.claim_next()
        with self.service() as session:
            job = session.get(GenerationJobRecord, first_id)
            job.lease_until = utcnow() - timedelta(seconds=1)
        other = JobRunner(self.sessions, SKILLS, lambda kind: self.models[kind],
                          "second-worker", allow_draft=True)
        second_id, second_attempt, _ = other.claim_next()
        self.assertEqual((first_id, first_attempt + 1), (second_id, second_attempt))
        with self.service() as session:
            with self.assertRaisesRegex(BusinessError, "JOB_LEASE_LOST"):
                MVPService(session, SKILLS, allow_draft=True).accept_topic(
                    first_id, "test-worker", first_attempt,
                    TopicResponse.model_validate(EXAMPLES["topic_response"]),
                )
        with self.service() as session:
            MVPService(session, SKILLS, allow_draft=True).accept_topic(
                second_id, other.worker_id, second_attempt,
                TopicResponse.model_validate(EXAMPLES["topic_response"]),
            )
        with self.service() as session:
            self.assertEqual(MVPService(session, SKILLS, allow_draft=True).current_topic(
                self.actor, project,
            ).status, "PENDING_APPROVAL")

    async def test_new_approved_topic_archives_old_working_copy(self):
        project = self.create_project()
        with self.service() as session:
            MVPService(session, SKILLS, allow_draft=True).start_topic(
                self.actor, project, StartGeneration(idempotency_key="t1"),
            )
        await self.runner.run_once()
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            first = service.current_topic(self.actor, project)
            service.decide_topic(self.actor, first.id, DecideTopic(expected_version=1, decision="APPROVED"))
            service.start_framework(self.actor, project, StartFramework(
                idempotency_key="f1", approved_topic_analysis_id=first.id, expected_topic_version=1,
            ))
        await self.runner.run_once()
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            old = service.project_working(self.actor, project)
            second = service.revise_topic(self.actor, first.id, ReviseTopic(
                expected_version=1, idempotency_key="edit", content=first.content,
            ))
            service.decide_topic(self.actor, second.id, DecideTopic(expected_version=2, decision="APPROVED"))
            service.start_framework(self.actor, project, StartFramework(
                idempotency_key="f2", approved_topic_analysis_id=second.id, expected_topic_version=2,
            ))
        await self.runner.run_once()
        with self.service() as session:
            service = MVPService(session, SKILLS, allow_draft=True)
            newer = service.project_working(self.actor, project)
            archives = service.list_working_archives(self.actor, project)
            self.assertEqual(newer.approved_topic_analysis_id, second.id)
            self.assertEqual(newer.edit_version, old.edit_version + 1)
            self.assertEqual(len(archives), 1)
            self.assertEqual(archives[0].case, old.case)
            self.assertEqual(archives[0].approved_topic_analysis_id, first.id)
            with self.assertRaisesRegex(BusinessError, "PROJECT_NOT_FOUND"):
                service.list_working_archives(self.other_actor, project)

    async def test_http_is_closed_without_auth_and_works_with_trusted_dependency(self):
        client = TestClient(app)
        response = client.post("/api/v1/projects", json={
            "motion": "题", "side": "反", "format": "4v4", "duration_seconds": 240,
        }, headers={"X-User-ID": str(self.actor)})
        self.assertEqual(response.status_code, 503)

        def trusted_service():
            with self.service() as session:
                yield MVPService(session, SKILLS, allow_draft=True)

        app.dependency_overrides[require_actor] = lambda: self.actor
        app.dependency_overrides[get_service] = trusted_service
        try:
            created = client.post("/api/v1/projects", json={
                "motion": "题", "side": "反", "format": "4v4", "duration_seconds": 240,
            })
            self.assertEqual(created.status_code, 201)
            project_id = created.json()["id"]
            queued = client.post(f"/api/v1/projects/{project_id}/topic-analysis-runs",
                                 json={"idempotency_key": "one"})
            self.assertEqual(queued.status_code, 202)
            self.assertEqual(client.get(f"/api/v1/jobs/{queued.json()['job_id']}").json()["status"], "QUEUED")
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
