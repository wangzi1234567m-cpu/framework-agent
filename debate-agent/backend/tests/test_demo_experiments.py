import copy
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.mock import SKILL_ROOT, SyntheticModel, synthetic_pair
from app.agents.runtime import AgentFailure, TopicAnalyzer
from app.schemas.agent import TopicRequest
from app.agents.skills import SkillRegistry
from app.demo import create_demo_app
from app.experiments import no_skill, run_pair, write_results
from app.infrastructure.llm.openai_compatible import OpenAICompatibleModel, output_budget
from app.main import app as production_app


class DemoTests(unittest.TestCase):
    def test_real_local_background_worker_persists_unapproved_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "workbench.sqlite"
            calls = []

            class LocalModel(SyntheticModel):
                model = "mock-v1"

                async def complete(self, stage, instructions, payload):
                    calls.append((self.kind, stage))
                    return await super().complete(stage, instructions, payload)

            def create():
                return create_demo_app(real=True, database_path=database, model_factory=LocalModel)

            def wait(client, job_id):
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    job = client.get(f"/api/v1/jobs/{job_id}").json()
                    if job["status"] in {"SUCCEEDED", "FAILED"}:
                        self.assertEqual(job["status"], "SUCCEEDED", job)
                        return
                    time.sleep(0.02)
                self.fail("Local background worker did not finish")

            with TestClient(create(), base_url="http://127.0.0.1:8001") as client:
                self.assertEqual(client.get("/demo/config").json()["mode"], "REAL")
                self.assertEqual(client.get("/demo/config", headers={"Origin": "https://remote.invalid"}).status_code, 403)
                data = client.get("/demo/config").json()["project"]
                project_id = client.post("/api/v1/projects", json=data).json()["id"]
                job_id = client.post(f"/api/v1/projects/{project_id}/topic-analysis-runs",
                                     json={"idempotency_key": "topic"}).json()["job_id"]
                self.assertTrue(client.post("/demo/run-next").json()["scheduled"])
                wait(client, job_id)
                topic = client.get(f"/api/v1/projects/{project_id}/topic-analyses/current").json()
                self.assertNotEqual(topic["status"], "APPROVED")
                client.post(f'/api/v1/topic-analyses/{topic["id"]}/approval', json={
                    "expected_version": topic["version"], "decision": "APPROVED",
                    "comment": "AUTOMATED_TEST_ONLY: not a user review",
                }).raise_for_status()
                job_id = client.post(f"/api/v1/projects/{project_id}/framework-runs", json={
                    "idempotency_key": "framework", "approved_topic_analysis_id": topic["id"],
                    "expected_topic_version": topic["version"],
                }).json()["job_id"]
                # No run-next call: the continuous local worker also consumes queued jobs.
                wait(client, job_id)
                candidate = client.get(f"/api/v1/projects/{project_id}/working-copy").json()
                exported = client.get(f"/demo/projects/{project_id}/candidate-export")
                self.assertIn("非正式版本", exported.text)
                self.assertIn("不代表用户审核", exported.text)
                self.assertIn(candidate["case"]["thesis"], exported.text)
                argument = candidate["case"]["arguments"][0]
                node = argument["reasoning_nodes"][0]
                self.assertIn(f'[{node["kind"]}]', exported.text)
                self.assertIn(argument["attack_defense"][0]["weighing"], exported.text)
                self.assertTrue(client.get("/demo/session").json()["test_confirmation"])
                with client.app.state.sessions() as session:
                    from app.models.p1 import CaseRevisionRecord
                    from sqlalchemy import select
                    self.assertIsNone(session.scalar(select(CaseRevisionRecord)))
            count = len(calls)
            with TestClient(create(), base_url="http://127.0.0.1:8001") as client:
                self.assertEqual(client.get("/demo/session").json()["project_id"], project_id)
                self.assertTrue(client.get("/demo/session").json()["test_confirmation"])
                self.assertEqual(client.get(f"/api/v1/projects/{project_id}/working-copy").json(), candidate)
                self.assertEqual(len(calls), count)

    def test_output_budgets_are_long_and_overridable(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(output_budget("TOPIC"), 16384)
            self.assertEqual(output_budget("FRAMEWORK"), 32768)
        with patch.dict(os.environ, {"LLM_TOPIC_MAX_TOKENS": "20000"}):
            self.assertEqual(output_budget("TOPIC"), 20000)
        with patch.dict(os.environ, {"LLM_FRAMEWORK_MAX_TOKENS": "0"}):
            with self.assertRaises(ValueError):
                output_budget("FRAMEWORK")

    def test_local_demo_closes_loop_without_opening_production_auth(self):
        with TestClient(create_demo_app(), base_url="http://127.0.0.1:8001") as client:
            input_data = client.get("/demo/config").json()["project"]
            project = client.post("/api/v1/projects", json=input_data).json()
            project_id = project["id"]
            premature = client.post(f"/api/v1/projects/{project_id}/framework-runs", json={
                "idempotency_key": "premature", "approved_topic_analysis_id": project_id,
                "expected_topic_version": 1,
            })
            self.assertEqual(premature.status_code, 409)
            job = client.post(f"/api/v1/projects/{project_id}/topic-analysis-runs",
                              json={"idempotency_key": "topic"}).json()
            self.assertTrue(client.post("/demo/run-next").json()["processed"])
            self.assertEqual(client.get(f'/api/v1/jobs/{job["job_id"]}').json()["status"], "SUCCEEDED")
            topic = client.get(f"/api/v1/projects/{project_id}/topic-analyses/current").json()
            content = {**topic["content"], "background": "Mock reviewed background"}
            topic = client.post(f'/api/v1/topic-analyses/{topic["id"]}/revisions', json={
                "expected_version": topic["version"], "idempotency_key": "edit-topic", "content": content,
            }).json()
            self.assertEqual(topic["content"]["background"], "Mock reviewed background")
            approved = client.post(f'/api/v1/topic-analyses/{topic["id"]}/approval', json={
                "expected_version": topic["version"], "decision": "APPROVED",
            })
            self.assertEqual(approved.status_code, 200)
            accepted = client.post(f"/api/v1/projects/{project_id}/framework-runs", json={
                "idempotency_key": "framework", "approved_topic_analysis_id": topic["id"],
                "expected_topic_version": topic["version"],
            })
            self.assertEqual(accepted.status_code, 202)
            self.assertTrue(client.post("/demo/run-next").json()["processed"])
            working = client.get(f"/api/v1/projects/{project_id}/working-copy").json()
            case = copy.deepcopy(working["case"])
            case["thesis"] += "（人工修改）"
            saved = client.patch(f'/api/v1/cases/{working["id"]}/working-copy', json={
                "expected_edit_version": working["edit_version"], "case": case,
            }).json()
            revision = client.post(f'/api/v1/cases/{working["id"]}/revisions', json={
                "expected_edit_version": saved["edit_version"], "idempotency_key": "revision",
            })
            self.assertEqual(revision.status_code, 201)
            exported = client.get(f'/api/v1/case-revisions/{revision.json()["id"]}/export')
            self.assertEqual(exported.status_code, 200)
            self.assertIn("人工修改", exported.text)
        with TestClient(production_app) as client:
            self.assertEqual(client.post("/api/v1/projects", json=input_data).status_code, 503)

    def test_demo_rejects_remote_hosts_origins_and_nonfixture_motion(self):
        with TestClient(create_demo_app(), base_url="http://127.0.0.1:8001") as client:
            self.assertEqual(client.get("/demo/config", headers={"Host": "attacker.example"}).status_code, 403)
            self.assertEqual(client.post("/demo/run-next", headers={"Origin": "https://attacker.example"}).status_code, 403)
            data = client.get("/demo/config").json()["project"]
            data["motion"] = "Not the fixture"
            self.assertEqual(client.post("/api/v1/projects", json=data).status_code, 422)


class ExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_provider_content_is_preserved_without_secret_headers(self):
        client_type = httpx.AsyncClient
        pack = SkillRegistry(SKILL_ROOT).load("TOPIC", "0.1.0", allow_draft=True)
        for finish_reason, expected in (("stop", "LLM_RESPONSE_INVALID"), ("length", "LLM_OUTPUT_TRUNCATED")):
            def respond(request):
                return httpx.Response(200, json={
                    "choices": [{"message": {"content": "{not valid JSON"}, "finish_reason": finish_reason}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                })

            with patch.dict(os.environ, {"LLM_BASE_URL": "https://example.invalid/v1",
                                         "LLM_API_KEY": "private-test-key", "LLM_MODEL": "same-test-model"}):
                with patch("app.infrastructure.llm.openai_compatible.httpx.AsyncClient",
                           side_effect=lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs)):
                    pair = await run_pair(synthetic_pair("TOPIC")["request"], pack, OpenAICompatibleModel)
            for result in pair:
                self.assertEqual(result["error_code"], expected)
                self.assertEqual(result["call_count"], 1)
                self.assertEqual(result["calls"][0]["completion"],
                                 {"content": "{not valid JSON", "finish_reason": finish_reason})
                self.assertNotIn("private-test-key", json.dumps(result))

    async def test_business_agent_receives_schema_without_experiment_wrapper(self):
        instructions_seen = []

        class CapturingModel(SyntheticModel):
            async def complete(self, stage, instructions, payload):
                instructions_seen.append((stage, instructions))
                return await super().complete(stage, instructions, payload)

        pack = SkillRegistry(SKILL_ROOT).load("TOPIC", "0.1.0", allow_draft=True)
        await TopicAnalyzer(pack, CapturingModel("TOPIC")).run(
            TopicRequest.model_validate(synthetic_pair("TOPIC")["request"])
        )
        self.assertEqual(len(instructions_seen), 3)
        for stage, instructions in instructions_seen:
            self.assertEqual(instructions.count("Required output JSON Schema:"), 1)
            schema = json.loads(instructions.split("Required output JSON Schema:\n")[1])
            if stage == "draft":
                self.assertIn("background", schema["$defs"]["TopicAnalysisContent"]["properties"])
            elif stage == "review":
                self.assertIn("findings", schema["properties"])

    async def test_real_transport_uses_same_model_budget_and_records_token_cost_without_network(self):
        bodies = []

        def respond(request):
            body = json.loads(request.content)
            bodies.append(body)
            stage = json.loads(body["messages"][1]["content"])["stage"]
            value = ({"summary": "test"} if stage == "analyze" else {"findings": []} if stage == "review"
                     else synthetic_pair("FRAMEWORK")["response"])
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(value)}}],
                                            "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

        client_type = httpx.AsyncClient
        with patch.dict(os.environ, {"LLM_BASE_URL": "https://example.invalid/v1",
                                     "LLM_API_KEY": "synthetic-not-a-real-key", "LLM_MODEL": "same-test-model"}):
            with patch("app.infrastructure.llm.openai_compatible.httpx.AsyncClient",
                       side_effect=lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs)):
                pack = SkillRegistry(SKILL_ROOT).load("FRAMEWORK", "0.1.0", allow_draft=True)
                pair = await run_pair(synthetic_pair("FRAMEWORK")["request"], pack,
                                      lambda: OpenAICompatibleModel(temperature=0, max_tokens=512),
                                      input_price=1, output_price=2)
        self.assertEqual(len(bodies), 10)
        self.assertTrue(all(body["model"] == "same-test-model" and body["temperature"] == 0
                            and body["max_tokens"] == 512 for body in bodies))
        for result in pair:
            self.assertEqual(result["usage"], {"prompt_tokens": 50, "completion_tokens": 25})
            self.assertAlmostEqual(result["estimated_cost"], 0.0001)
            self.assertNotIn("synthetic-not-a-real-key", json.dumps(result))

    async def test_same_input_fixed_budget_and_no_proprietary_text_in_baseline(self):
        pack = SkillRegistry(SKILL_ROOT).load("FRAMEWORK", "0.1.0", allow_draft=True)
        pair = await run_pair(synthetic_pair("FRAMEWORK")["request"], pack,
                              lambda: SyntheticModel("FRAMEWORK"))
        self.assertEqual(len(pair), 2)
        self.assertEqual(pair[0]["input"], pair[1]["input"])
        self.assertEqual(pair[0]["input_sha256"], pair[1]["input_sha256"])
        for result in pair:
            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertEqual(result["call_count"], 5)
            self.assertEqual([call["stage"] for call in result["calls"]],
                             ["analyze", "draft", "review", "revise", "review"])
            self.assertIsNone(result["quality_score"])
            self.assertIsNone(result["estimated_cost"])
        baseline = next(result for result in pair if result["arm"] == "WITHOUT_SKILL")
        for call in baseline["calls"]:
            self.assertNotIn(pack.instructions, call["instructions"])
            self.assertEqual(call["instructions"].count("Required output JSON Schema:"), 1)
            self.assertEqual(call["output_schema"], next(result for result in pair if result["arm"] == "WITH_SKILL")
                             ["calls"][baseline["calls"].index(call)]["output_schema"])
        self.assertNotEqual(no_skill(pack).sha256, pack.sha256)

    async def test_failure_is_preserved_and_blind_export_hides_arm(self):
        class FailingModel:
            async def complete(self, stage, instructions, payload):
                raise AgentFailure("LLM_TIMEOUT")
        pack = SkillRegistry(SKILL_ROOT).load("TOPIC", "0.1.0", allow_draft=True)
        pair = await run_pair(synthetic_pair("TOPIC")["request"], pack, FailingModel)
        self.assertTrue(all(result["status"] == "FAILED" for result in pair))
        for result in pair:
            result.update(case_id="case-1", repeat=1)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "results"
            write_results(folder, {"seed": 1}, pair)
            blind = json.loads((folder / "blind-review.json").read_text(encoding="utf-8"))
            self.assertEqual(len(blind), 2)
            self.assertTrue(all(row["status"] == "FAILED" for row in blind))
            self.assertTrue(all("arm" not in row and "calls" not in row for row in blind))
            self.assertEqual(len(json.loads((folder / "private-mapping.json").read_text())), 2)
            with self.assertRaises(FileExistsError):
                write_results(folder, {"seed": 1}, pair)
