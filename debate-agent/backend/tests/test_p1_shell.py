import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.schemas.agent import FrameworkRequest, FrameworkResponse
from app.services.candidate_materialization import materialize_framework

BACKEND = Path(__file__).resolve().parents[1]


class P1ShellTests(unittest.TestCase):
    def test_http_shell_is_reachable_and_business_routes_fail_closed(self):
        client = TestClient(app)
        self.assertEqual(client.get("/health").json(), {"status": "ok"})
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            response = client.get("/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "DATABASE_UNAVAILABLE")
        self.assertEqual(client.get("/openapi.json").status_code, 200)
        response = client.post("/api/v1/projects", json={
            "motion": "辩题", "side": "正方", "format": "4v4", "duration_seconds": 240,
        })
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "AUTH_NOT_CONFIGURED")
        response = client.post("/api/v1/projects", json={
            "motion": "辩题", "side": "正方", "format": "4v4", "duration_seconds": 0,
        })
        self.assertEqual(response.status_code, 503)

    def test_migration_applies_to_clean_sqlite_for_structural_smoke(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "p1.sqlite"
            url = f"sqlite+pysqlite:///{db.as_posix()}"
            config = Config(str(BACKEND / "alembic.ini"))
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(config, "head")
            engine = create_engine(url)
            try:
                self.assertTrue({
                    "projects", "topic_analyses", "working_copies", "case_revisions",
                    "approvals", "generation_jobs", "candidate_ref_mappings", "command_idempotency",
                    "working_copy_archives", "alembic_version",
                }.issubset(set(inspect(engine).get_table_names())))
            finally:
                engine.dispose()

    def test_framework_candidate_materializes_with_server_owned_ids(self):
        examples = json.loads((Path(__file__).with_name("p1_contract_examples.json")).read_text(encoding="utf-8"))
        request = FrameworkRequest.model_validate(examples["framework_request"])
        response = FrameworkResponse.model_validate(examples["framework_response"])
        case, mapping = materialize_framework(request, response, job_id=uuid4())
        self.assertEqual(case.definitions, request.approved_topic.definitions)
        self.assertEqual(case.judging_criteria, request.approved_topic.judging_criteria)
        self.assertEqual(len(mapping.candidate_ref_to_id), 4)
        self.assertEqual(case.arguments[0].id, mapping.candidate_ref_to_id["arg-1"])
        self.assertEqual(
            case.arguments[0].evidence_needs[0].target_node_id,
            mapping.candidate_ref_to_id["node-2"],
        )
        self.assertEqual(case.arguments[0].evidence_link_ids, [])


if __name__ == "__main__":
    unittest.main()
