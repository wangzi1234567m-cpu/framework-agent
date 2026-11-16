import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.agent import (
    ChangeResponse, FrameworkBuilderPort, FrameworkRequest, FrameworkResponse,
    TopicAnalyzerPort, TopicRequest, TopicResponse,
)
from app.schemas.api import CreateProject, ErrorResponse, ReviseTopic
from app.schemas.domain import (
    Argument,
    CandidateRefMapping,
    DebateCase,
    EvidenceItem,
    EvidenceNeed,
    HumanDecision,
    GenerationJob,
    ResearchMetadata,
    ReasoningNode,
    SourceLocator,
    TopicAnalysisContent,
)


def topic():
    return TopicAnalysisContent(
        discussion_scope="备赛人群",
        affirmative_position="更有利",
        negative_position="更有害",
    )


def case_with_tree():
    leaf = ReasoningNode(id=uuid4(), content="影响决策", order=0)
    root = ReasoningNode(id=uuid4(), content="形成压力", order=0, children=[leaf])
    argument = Argument(
        id=uuid4(), order=0, title="压力影响决策", core_claim="负担增加",
        explanation="解释发生条件", reasoning_nodes=[root],
        evidence_needs=[EvidenceNeed(id=uuid4(), target_node_id=leaf.id, question="是否出现影响", acceptable_source="原始研究")],
    )
    return DebateCase(motion="压力有利还是有害", side="反", thesis="更有害", arguments=[argument])


class ContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = json.loads(Path(__file__).with_name("p1_contract_examples.json").read_text(encoding="utf-8"))

    def test_recursive_tree_and_roundtrip(self):
        draft = case_with_tree()
        restored = DebateCase.model_validate_json(draft.model_dump_json())
        self.assertEqual(restored.arguments[0].reasoning_nodes[0].children[0].content, "影响决策")

    def test_duplicate_and_dangling_node_rejected(self):
        draft = case_with_tree()
        argument = draft.arguments[0].model_dump()
        argument["reasoning_nodes"][0]["children"][0]["id"] = argument["reasoning_nodes"][0]["id"]
        with self.assertRaises(ValidationError):
            Argument.model_validate(argument)
        argument = draft.arguments[0].model_dump()
        argument["evidence_needs"][0]["target_node_id"] = uuid4()
        with self.assertRaises(ValidationError):
            Argument.model_validate(argument)

    def test_candidate_cannot_claim_approval(self):
        with self.assertRaises(ValidationError):
            TopicResponse.model_validate({"analysis": topic().model_dump(), "status": "APPROVED"})
        with self.assertRaises(ValidationError):
            FrameworkResponse.model_validate({
                "thesis": "更有害",
                "arguments": case_with_tree().arguments,
                "approved_by": str(uuid4()),
            })

    def test_p1_request_response_handoff_examples(self):
        topic_request = TopicRequest.model_validate(self.examples["topic_request"])
        topic_response = TopicResponse.model_validate(self.examples["topic_response"])
        framework_request = FrameworkRequest.model_validate(self.examples["framework_request"])
        framework_response = FrameworkResponse.model_validate(self.examples["framework_response"])
        self.assertEqual(topic_request.motion, framework_request.motion)
        self.assertEqual(topic_response.analysis, framework_request.approved_topic)
        self.assertEqual(framework_response.arguments[0].evidence_needs[0].target_node_ref, "node-2")
        self.assertEqual(
            FrameworkResponse.model_validate_json(framework_response.model_dump_json()),
            framework_response,
        )

    def test_p1_rejects_invalid_candidate_refs_and_business_fields(self):
        for name, response in self.examples["invalid_responses"].items():
            with self.subTest(name=name), self.assertRaises(ValidationError):
                FrameworkResponse.model_validate(response)
        valid = self.examples["framework_response"]
        with self.assertRaises(ValidationError):
            FrameworkResponse.model_validate({**valid, "status": "APPROVED"})
        with self.assertRaises(ValidationError):
            FrameworkResponse.model_validate({**valid, "arguments": [{**valid["arguments"][0], "id": str(uuid4())}]})
        with self.assertRaises(ValidationError):
            FrameworkResponse.model_validate({
                **valid,
                "arguments": [{**valid["arguments"][0], "evidence_link_ids": [str(uuid4())]}],
            })
        with self.assertRaises(ValidationError):
            FrameworkResponse.model_validate({
                **valid,
                "arguments": [
                    valid["arguments"][0],
                    {**valid["arguments"][0], "ref": "arg-2", "order": 0},
                ],
            })

    def test_service_owned_mapping_and_topic_revision_command(self):
        mapping = CandidateRefMapping(
            job_id=uuid4(), request_id=uuid4(),
            candidate_ref_to_id={"arg-1": uuid4(), "node-1": uuid4(), "node-2": uuid4(), "need-1": uuid4()},
        )
        self.assertEqual(len(set(mapping.candidate_ref_to_id.values())), 4)
        with self.assertRaises(ValidationError):
            CandidateRefMapping(
                job_id=uuid4(), request_id=uuid4(),
                candidate_ref_to_id={"arg-1": mapping.candidate_ref_to_id["arg-1"], "node-1": mapping.candidate_ref_to_id["arg-1"]},
            )
        revised = ReviseTopic(expected_version=1, idempotency_key="revise-1", content=self.examples["topic_response"]["analysis"])
        self.assertEqual(revised.expected_version, 1)
        with self.assertRaises(ValidationError):
            ReviseTopic.model_validate({**revised.model_dump(), "status": "APPROVED"})

    def test_evidence_locator_and_grade_not_a_human_decision(self):
        source_id = uuid4()
        item = EvidenceItem(
            id=uuid4(), project_id=uuid4(), evidence_type="RESEARCH",
            factual_claim="待核验", summary="仅记录来源线索", source_ids=[source_id],
            locators=[SourceLocator(source_id=source_id, page=1)],
        )
        self.assertEqual(item.human_decision, HumanDecision.PENDING)
        with self.assertRaises(ValidationError):
            EvidenceItem.model_validate({**item.model_dump(), "locators": [{"source_id": str(uuid4())}]})
        with self.assertRaises(ValidationError):
            EvidenceItem.model_validate({**item.model_dump(), "source_grade": "F"})
        with self.assertRaises(ValidationError):
            ResearchMetadata(sample_size=-1)
        with self.assertRaises(ValidationError):
            EvidenceItem.model_validate({**item.model_dump(), "research_metadata": {"invented_field": "无来源"}})

    def test_ambiguous_change_must_request_clarification(self):
        self.assertEqual(ChangeResponse(clarification_question="哪个论点？").proposal, None)
        with self.assertRaises(ValidationError):
            ChangeResponse()

    def test_api_version_and_error_envelope(self):
        with self.assertRaises(ValidationError):
            CreateProject(motion="辩题", side="正", format="四辩", duration_seconds=0)
        with self.assertRaises(ValidationError):
            ErrorResponse(error_code="CONFLICT", message="版本冲突", request_id="not-a-uuid")

    def test_job_timestamps_require_timezone(self):
        fields = dict(
            id=uuid4(), project_id=uuid4(), job_type="TOPIC", current_step="ANALYZE_TOPIC",
            input_snapshot={}, idempotency_key="abc", created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.assertEqual(GenerationJob(**fields).attempt, 0)
        with self.assertRaises(ValidationError):
            GenerationJob(**{**fields, "created_at": datetime(2026, 1, 1)})


class AgentPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_agent_ports_with_contract_mocks(self):
        examples = json.loads(Path(__file__).with_name("p1_contract_examples.json").read_text(encoding="utf-8"))

        class MockTopicAnalyzer:
            async def run(self, request: TopicRequest) -> TopicResponse:
                assert request.motion == examples["topic_request"]["motion"]
                return TopicResponse.model_validate(examples["topic_response"])

        class MockFrameworkBuilder:
            async def run(self, request: FrameworkRequest) -> FrameworkResponse:
                assert request.approved_topic_analysis_id is not None
                return FrameworkResponse.model_validate(examples["framework_response"])

        topic_agent: TopicAnalyzerPort = MockTopicAnalyzer()
        framework_agent: FrameworkBuilderPort = MockFrameworkBuilder()
        topic_result = await topic_agent.run(TopicRequest.model_validate(examples["topic_request"]))
        framework_result = await framework_agent.run(FrameworkRequest.model_validate(examples["framework_request"]))
        self.assertEqual(topic_result.analysis, FrameworkRequest.model_validate(examples["framework_request"]).approved_topic)
        self.assertEqual(framework_result.arguments[0].ref, "arg-1")


if __name__ == "__main__":
    unittest.main()
