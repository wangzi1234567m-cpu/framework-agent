"""Boundary DTOs: Agent outputs are proposals, never approved business records."""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from .domain import Argument, AttackDefense, Contract, DebateCase, EvidenceNeed, SourceLocator, TopicAnalysisContent


class AgentContext(Contract):
    project_id: UUID
    schema_version: Literal[1] = 1
    rule_set_version: str
    skill_version: str
    request_id: UUID


class TopicRequest(Contract):
    context: AgentContext
    motion: str
    side: str
    format: str
    duration_seconds: int = Field(gt=0)
    competition_context: str = ""
    user_requirements: str = ""


class TopicResponse(Contract):
    analysis: TopicAnalysisContent
    uncertainty_notes: list[str] = Field(default_factory=list)


class FrameworkRequest(Contract):
    context: AgentContext
    motion: str
    side: str
    format: str
    duration_seconds: int = Field(gt=0)
    competition_context: str = ""
    user_requirements: str = ""
    approved_topic_analysis_id: UUID
    topic_version: int = Field(ge=1)
    approved_topic: TopicAnalysisContent
    base_edit_version: int | None = Field(default=None, ge=1)


class CandidateReasoningNode(Contract):
    ref: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    label: str = ""
    kind: str = "other"
    content: str = Field(min_length=1)
    order: int = Field(ge=0)
    children: list[CandidateReasoningNode] = Field(default_factory=list)


class CandidateEvidenceNeed(Contract):
    ref: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    target_node_ref: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    question: str = Field(min_length=1)
    acceptable_source: str = Field(min_length=1)


class CandidateArgument(Contract):
    ref: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    order: int = Field(ge=0)
    title: str = Field(min_length=1)
    core_claim: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    reasoning_nodes: list[CandidateReasoningNode] = Field(min_length=1)
    impact: str = Field(min_length=1)
    evidence_needs: list[CandidateEvidenceNeed] = Field(default_factory=list)
    attack_defense: list[AttackDefense] = Field(default_factory=list)


class FrameworkResponse(Contract):
    thesis: str = Field(min_length=1)
    arguments: list[CandidateArgument] = Field(min_length=1)
    weighing: str = ""
    overall_strategy: str = ""
    uncertainty_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_local_refs(self) -> FrameworkResponse:
        refs: set[str] = set()
        argument_orders: set[int] = set()

        def register(ref: str) -> None:
            if ref in refs:
                raise ValueError(f"duplicate candidate ref: {ref}")
            refs.add(ref)

        def walk(nodes: list[CandidateReasoningNode], local_nodes: set[str]) -> None:
            orders: set[int] = set()
            for node in nodes:
                if node.order in orders:
                    raise ValueError("duplicate sibling reasoning order")
                orders.add(node.order)
                register(node.ref)
                local_nodes.add(node.ref)
                walk(node.children, local_nodes)

        for argument in self.arguments:
            if argument.order in argument_orders:
                raise ValueError("duplicate argument order")
            argument_orders.add(argument.order)
            register(argument.ref)
            local_nodes: set[str] = set()
            walk(argument.reasoning_nodes, local_nodes)
            for need in argument.evidence_needs:
                register(need.ref)
                if need.target_node_ref is not None and need.target_node_ref not in local_nodes:
                    raise ValueError("evidence need references a node outside its argument")
        return self


class TopicAnalyzerPort(Protocol):
    async def run(self, request: TopicRequest) -> TopicResponse: ...


class FrameworkBuilderPort(Protocol):
    async def run(self, request: FrameworkRequest) -> FrameworkResponse: ...


class ResearchRequest(Contract):
    context: AgentContext
    argument: Argument
    needs: list[EvidenceNeed] = Field(min_length=1)


class SourceLead(Contract):
    title: str
    url: str
    publisher: str | None = None
    note: str = ""


class ResearchResponse(Contract):
    leads: list[SourceLead] = Field(default_factory=list)
    unresolved_need_ids: list[UUID] = Field(default_factory=list)


class EvidenceVerificationRequest(Contract):
    context: AgentContext
    factual_claim: str
    evidence_type: Literal["DATA", "RESEARCH", "REAL_CASE", "OTHER"]
    sources: list[SourceLead]
    locators: list[SourceLocator] = Field(default_factory=list)
    supported_claim: str


class EvidenceVerificationResponse(Contract):
    proposed_grade: Literal["A", "B", "C", "D", "X"] | None = None
    trace_complete: bool = False
    factual_accuracy_notes: list[str] = Field(default_factory=list)
    relevance_score: int | None = Field(default=None, ge=1, le=5)
    relevance_explanation: str = ""
    limitations: list[str] = Field(default_factory=list)
    cannot_prove: str = ""


class FrameworkReviewRequest(Contract):
    context: AgentContext
    candidate_case: DebateCase


class ReviewFinding(Contract):
    target_id: UUID
    rule_id: str
    issue: str
    suggested_fix: str
    score: int | None = Field(default=None, ge=1, le=5)


class FrameworkReviewResponse(Contract):
    findings: list[ReviewFinding] = Field(default_factory=list)


class SpeechRequest(Contract):
    context: AgentContext
    case_revision_id: UUID
    confirmed_case: DebateCase
    approved_evidence_ids: list[UUID]
    duration_seconds: int = Field(gt=0)
    format: str


class SpeechSectionCandidate(Contract):
    text: str
    dependency_refs: list[UUID] = Field(min_length=1)
    evidence_ids: list[UUID] = Field(default_factory=list)


class SpeechResponse(Contract):
    sections: list[SpeechSectionCandidate] = Field(min_length=1)
    change_suggestions: list[str] = Field(default_factory=list)


class ChangeRequest(Contract):
    context: AgentContext
    instruction: str
    base_edit_version: int = Field(ge=1)
    working_copy: DebateCase


class ChangeCandidate(Contract):
    target_id: UUID
    operation: Literal["ADD", "UPDATE", "DELETE", "REORDER", "LINK", "UNLINK"]
    patch: dict
    before_snapshot: dict
    after_snapshot: dict


class ChangeResponse(Contract):
    proposal: ChangeCandidate | None = None
    clarification_question: str | None = None

    @model_validator(mode="after")
    def exactly_one_outcome(self) -> ChangeResponse:
        if (self.proposal is None) == (self.clarification_question is None):
            raise ValueError("return either a proposal or a clarification question")
        return self
