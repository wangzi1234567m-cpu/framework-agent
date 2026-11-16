"""Pure conversion of accepted P1 candidates; callers enforce approvals and idempotency."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from app.schemas.agent import CandidateReasoningNode, FrameworkRequest, FrameworkResponse
from app.schemas.domain import (
    Argument, CandidateRefMapping, DebateCase, EvidenceNeed, ReasoningNode,
)


def materialize_framework(
    request: FrameworkRequest,
    response: FrameworkResponse,
    job_id: UUID,
    new_id: Callable[[], UUID] = uuid4,
) -> tuple[DebateCase, CandidateRefMapping]:
    """Only call after a transaction verifies current topic and base edit versions."""
    response = FrameworkResponse.model_validate_json(response.model_dump_json())
    assigned: dict[str, UUID] = {}

    def identifier(ref: str) -> UUID:
        assigned[ref] = new_id()
        return assigned[ref]

    def node(candidate: CandidateReasoningNode) -> ReasoningNode:
        return ReasoningNode(
            id=identifier(candidate.ref),
            label=candidate.label,
            kind=candidate.kind,
            content=candidate.content,
            order=candidate.order,
            children=[node(child) for child in candidate.children],
        )

    arguments: list[Argument] = []
    for candidate in response.arguments:
        argument_id = identifier(candidate.ref)
        reasoning_nodes = [node(root) for root in candidate.reasoning_nodes]
        needs = [
            EvidenceNeed(
                id=identifier(need.ref),
                target_node_id=assigned[need.target_node_ref] if need.target_node_ref else None,
                question=need.question,
                acceptable_source=need.acceptable_source,
            )
            for need in candidate.evidence_needs
        ]
        arguments.append(
            Argument(
                id=argument_id,
                order=candidate.order,
                title=candidate.title,
                core_claim=candidate.core_claim,
                explanation=candidate.explanation,
                reasoning_nodes=reasoning_nodes,
                impact=candidate.impact,
                evidence_needs=needs,
                attack_defense=candidate.attack_defense,
            )
        )

    case = DebateCase(
        motion=request.motion,
        side=request.side,
        thesis=response.thesis,
        definitions=request.approved_topic.definitions,
        judging_criteria=request.approved_topic.judging_criteria,
        weighing=response.weighing,
        arguments=arguments,
        overall_strategy=response.overall_strategy,
    )
    mapping = CandidateRefMapping(
        job_id=job_id, request_id=request.context.request_id, candidate_ref_to_id=assigned,
    )
    return case, mapping
