"""V1 review-draft domain contracts; persistence and approval live in services."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TopicStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TraceStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    SOURCE_LOCATED = "SOURCE_LOCATED"
    TRACE_INCOMPLETE = "TRACE_INCOMPLETE"
    TRACED = "TRACED"


class VerificationStatus(StrEnum):
    NOT_REVIEWED = "NOT_REVIEWED"
    AI_REVIEWED = "AI_REVIEWED"
    DISPUTED = "DISPUTED"


class HumanDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_MORE_SOURCE = "NEEDS_MORE_SOURCE"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReasoningNode(Contract):
    id: UUID
    label: str = ""
    kind: str = "other"
    content: str
    order: int = Field(ge=0)
    children: list[ReasoningNode] = Field(default_factory=list)


class EvidenceNeed(Contract):
    id: UUID
    target_node_id: UUID | None = None
    question: str
    acceptable_source: str
    status: Literal["OPEN", "RESOLVED"] = "OPEN"


class AttackDefense(Contract):
    opposing_claim: str
    response: str
    weighing: str = ""


class Argument(Contract):
    id: UUID
    order: int = Field(ge=0)
    title: str
    core_claim: str
    explanation: str
    reasoning_nodes: list[ReasoningNode] = Field(default_factory=list)
    impact: str = ""
    evidence_link_ids: list[UUID] = Field(default_factory=list)
    evidence_needs: list[EvidenceNeed] = Field(default_factory=list)
    attack_defense: list[AttackDefense] = Field(default_factory=list)
    extension_data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_tree(self) -> Argument:
        ids: set[UUID] = {self.id}

        def walk(nodes: list[ReasoningNode]) -> None:
            for node in nodes:
                if node.id in ids:
                    raise ValueError("argument and reasoning node IDs must be unique")
                ids.add(node.id)
                walk(node.children)

        walk(self.reasoning_nodes)
        for need in self.evidence_needs:
            if need.target_node_id is not None and need.target_node_id not in ids:
                raise ValueError("evidence need references an unknown node")
        return self


class DebateCase(Contract):
    schema_version: Literal[1] = 1
    motion: str
    side: str
    thesis: str
    definitions: dict[str, str] = Field(default_factory=dict)
    judging_criteria: list[str] = Field(default_factory=list)
    weighing: str = ""
    arguments: list[Argument] = Field(default_factory=list)
    overall_strategy: str = ""
    attack_defense: list[AttackDefense] = Field(default_factory=list)
    conclusion: str = ""

    @model_validator(mode="after")
    def validate_ids(self) -> DebateCase:
        ids: set[UUID] = set()
        for argument in self.arguments:
            if argument.id in ids:
                raise ValueError("duplicate argument ID")
            ids.add(argument.id)
            stack = list(argument.reasoning_nodes)
            while stack:
                node = stack.pop()
                if node.id in ids:
                    raise ValueError("duplicate reasoning node ID across arguments")
                ids.add(node.id)
                stack.extend(node.children)
        return self


class DefinitionNote(Contract):
    term: str
    source_id: str
    quote: str
    explanation: str


class TopicAnalysisContent(Contract):
    background: str = Field(default="", description="Topic context; unverified facts remain explicitly uncertain.")
    target_audience: str = Field(default="", description="People covered by the topic, not the readership of the draft.")
    definitions: dict[str, str] = Field(default_factory=dict)
    definition_notes: list[DefinitionNote] = Field(default_factory=list)
    discussion_scope: str = Field(default="", description="Legacy internal field; omit in new concise output.")
    assumptions: list[str] = Field(default_factory=list)
    core_conflicts: list[str] = Field(default_factory=list)
    affirmative_position: str = ""
    negative_position: str = ""
    clash_points: list[str] = Field(default_factory=list)
    judging_criteria: list[str] = Field(default_factory=list)
    strategy_options: list[str] = Field(default_factory=list)
    opponent_attacks: list[str] = Field(default_factory=list)


class TopicAnalysis(Contract):
    id: UUID
    project_id: UUID
    version: int = Field(ge=1)
    content: TopicAnalysisContent
    status: TopicStatus = TopicStatus.DRAFT


class WorkingCopy(Contract):
    id: UUID
    project_id: UUID
    edit_version: int = Field(ge=1)
    approved_topic_analysis_id: UUID
    case: DebateCase
    updated_at: AwareDatetime


class ArchivedWorkingCopy(Contract):
    id: UUID
    project_id: UUID
    original_working_copy_id: UUID
    edit_version: int = Field(ge=1)
    approved_topic_analysis_id: UUID
    case: DebateCase
    archived_at: AwareDatetime


class CandidateRefMapping(Contract):
    """Service-owned audit mapping for one accepted framework candidate."""

    job_id: UUID
    request_id: UUID
    candidate_ref_to_id: dict[str, UUID]

    @model_validator(mode="after")
    def validate_mapping(self) -> CandidateRefMapping:
        if any(re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", ref) is None for ref in self.candidate_ref_to_id):
            raise ValueError("invalid candidate ref in mapping")
        if len(set(self.candidate_ref_to_id.values())) != len(self.candidate_ref_to_id):
            raise ValueError("candidate refs must map to distinct business IDs")
        return self


class CaseRevision(Contract):
    id: UUID
    project_id: UUID
    revision_number: int = Field(ge=1)
    source_edit_version: int = Field(ge=1)
    approved_topic_analysis_id: UUID
    snapshot: DebateCase
    approved_by: UUID
    approved_at: AwareDatetime


class SourceRecord(Contract):
    id: UUID
    title: str
    publisher: str | None = None
    author: str | None = None
    source_type: str
    canonical_url: str | None = None
    doi: str | None = None
    document_url: str | None = None
    published_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime
    content_hash: str | None = None
    source_grade: Literal["A", "B", "C", "D", "X"] | None = None


class SourceLocator(Contract):
    source_id: UUID
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    table: str | None = None
    quote: str | None = None


class ResearchMetadata(Contract):
    research_type: str | None = None
    institution: str | None = None
    authors: list[str] = Field(default_factory=list)
    population: str | None = None
    sample_size: int | None = Field(default=None, ge=0)
    sampling_method: str | None = None
    collection_period: str | None = None
    geography: str | None = None
    methodology: str | None = None
    measurement_definition: str | None = None
    limitations: list[str] = Field(default_factory=list)


class CaseMetadata(Contract):
    subject_name: str | None = None
    organization: str | None = None
    event_date: str | None = None
    event_location: str | None = None
    event_description: str | None = None
    official_record_urls: list[str] = Field(default_factory=list)
    media_report_urls: list[str] = Field(default_factory=list)
    corroboration_sources: list[str] = Field(default_factory=list)


class EvidenceItem(Contract):
    id: UUID
    project_id: UUID
    evidence_type: Literal["DATA", "RESEARCH", "REAL_CASE", "OTHER"]
    factual_claim: str
    summary: str
    source_ids: list[UUID] = Field(default_factory=list)
    locators: list[SourceLocator] = Field(default_factory=list)
    research_metadata: ResearchMetadata | None = None
    case_metadata: CaseMetadata | None = None
    limitations: list[str] = Field(default_factory=list)
    trace_status: TraceStatus = TraceStatus.DISCOVERED
    verification_status: VerificationStatus = VerificationStatus.NOT_REVIEWED
    human_decision: HumanDecision = HumanDecision.PENDING
    source_grade: Literal["A", "B", "C", "D", "X"] | None = None

    @model_validator(mode="after")
    def validate_locators(self) -> EvidenceItem:
        if any(locator.source_id not in self.source_ids for locator in self.locators):
            raise ValueError("locator references a source not attached to this evidence")
        return self


class EvidenceLink(Contract):
    id: UUID
    project_id: UUID
    case_id: UUID
    evidence_id: UUID
    target_type: Literal["ARGUMENT", "REASONING_NODE"]
    target_id: UUID
    relation_type: Literal["SUPPORTS", "CONTRADICTS", "CONTEXTUALIZES"]
    supported_claim: str
    relevance_explanation: str
    cannot_prove: str = ""
    alternative_explanation: str = ""
    relevance_score: int | None = Field(default=None, ge=1, le=5)


class GenerationJob(Contract):
    id: UUID
    project_id: UUID
    job_type: str
    status: JobStatus = JobStatus.QUEUED
    current_step: str
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any] | None = None
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    idempotency_key: str
    lease_owner: str | None = None
    lease_until: AwareDatetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    rule_set_version: str | None = None
    skill_version: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Approval(Contract):
    id: UUID
    project_id: UUID
    target_type: Literal["TOPIC_ANALYSIS", "EVIDENCE", "CASE_REVISION"]
    target_id: UUID
    target_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED", "NEEDS_MORE_SOURCE"]
    reviewer_id: UUID
    created_at: AwareDatetime
    comment: str = ""


class ChangeProposal(Contract):
    id: UUID
    project_id: UUID
    working_copy_id: UUID
    base_edit_version: int = Field(ge=1)
    target_id: UUID
    operation: Literal["ADD", "UPDATE", "DELETE", "REORDER", "LINK", "UNLINK"]
    patch: dict[str, Any]
    before_snapshot: dict[str, Any]
    after_snapshot: dict[str, Any]
    status: Literal["PENDING", "ACCEPTED", "REJECTED", "CANCELLED"] = "PENDING"


class SpeechSection(Contract):
    id: UUID
    order: int = Field(ge=0)
    text: str
    dependency_refs: list[UUID]
    stale: bool = False


class SpeechDraft(Contract):
    id: UUID
    project_id: UUID
    source_revision_id: UUID
    version: int = Field(ge=1)
    duration_target_seconds: int = Field(gt=0)
    sections: list[SpeechSection]
