"""Bounded, model-independent execution shared by the two P1 agents."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import Field, ValidationError

from app.agents.skills import SkillPack
from app.schemas.agent import FrameworkRequest, FrameworkResponse, TopicRequest, TopicResponse
from app.schemas.domain import Contract


class AgentFailure(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Finding(Contract):
    target: str
    rule_id: str
    severity: str = Field(pattern=r"^(BLOCKING|IMPROVEMENT)$")
    issue: str
    suggested_fix: str


class Review(Contract):
    findings: list[Finding] = Field(default_factory=list)


class ModelPort(Protocol):
    async def complete(self, stage: str, instructions: str, payload: dict[str, Any]) -> dict[str, Any]: ...


Checkpoint = Callable[[str, dict[str, Any]], Awaitable[None]]


class WritingAgent:
    def __init__(self, skill: SkillPack, model: ModelPort, *, timeout_seconds: float = 180,
                 always_revise: bool = False):
        self.skill = skill
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.always_revise = always_revise

    async def _complete(self, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        instructions = self.skill.instructions + "\n\n" + self.skill.prompts[stage]
        output = TopicResponse if self.skill.manifest.agent_type == "TOPIC" else FrameworkResponse
        schema = Review.model_json_schema() if stage == "review" else (
            output.model_json_schema() if stage in {"draft", "revise"} else {"type": "object"}
        )
        # Business jobs and experiments must give the model the same DTO boundary.
        instructions += "\nRequired output JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
        try:
            value = await asyncio.wait_for(
                self.model.complete(stage, instructions, payload), timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            raise AgentFailure("LLM_TIMEOUT") from exc
        if not isinstance(value, dict):
            raise AgentFailure("CANDIDATE_SCHEMA_INVALID")
        return value

    async def _run(
        self,
        request: TopicRequest | FrameworkRequest,
        output_type: type[TopicResponse] | type[FrameworkResponse],
        checkpoint: Checkpoint | None,
    ) -> TopicResponse | FrameworkResponse:
        if request.context.skill_version != self.skill.manifest.skill_version:
            raise AgentFailure("SKILL_VERSION_MISMATCH")
        if request.context.rule_set_version != self.skill.manifest.rule_set_version:
            raise AgentFailure("RULE_SET_VERSION_MISMATCH")
        original = request.model_dump(mode="json")
        analysis = await self._complete("analyze", {"request": original})
        if checkpoint:
            await checkpoint("ANALYZE_INPUT", analysis)
        draft = await self._complete("draft", {"request": original, "analysis": analysis})
        if checkpoint:
            await checkpoint("DRAFT", draft)
        review = self._review(await self._complete("review", {"request": original, "candidate": draft}))
        if checkpoint:
            await checkpoint("SELF_REVIEW", review.model_dump(mode="json"))
        remaining = review
        if review.findings or self.always_revise:
            draft = await self._complete(
                "revise", {"request": original, "candidate": draft, "findings": review.model_dump(mode="json")},
            )
            if checkpoint:
                await checkpoint("REVISE_DRAFT", draft)
            final_review = self._review(await self._complete(
                "review", {"request": original, "candidate": draft, "final_check": True},
            ))
            if any(finding.severity == "BLOCKING" for finding in final_review.findings):
                raise AgentFailure("SELF_REVIEW_BLOCKED")
            remaining = final_review
        try:
            result = output_type.model_validate(draft)
        except ValidationError as exc:
            raise AgentFailure("CANDIDATE_SCHEMA_INVALID") from exc
        if remaining.findings:
            result = output_type.model_validate({
                **result.model_dump(mode="json"),
                "uncertainty_notes": result.uncertainty_notes + [
                    f"{finding.target}: {finding.issue}" for finding in remaining.findings
                ],
            })
        if checkpoint:
            await checkpoint("FINALIZE", {"validated": True})
        return result

    @staticmethod
    def _review(value: dict[str, Any]) -> Review:
        try:
            return Review.model_validate(value)
        except ValidationError as exc:
            raise AgentFailure("SELF_REVIEW_INVALID") from exc


class TopicAnalyzer(WritingAgent):
    async def run(self, request: TopicRequest, checkpoint: Checkpoint | None = None) -> TopicResponse:
        if self.skill.manifest.agent_type != "TOPIC":
            raise AgentFailure("SKILL_AGENT_MISMATCH")
        result = await self._run(request, TopicResponse, checkpoint)
        assert isinstance(result, TopicResponse)
        return result


class FrameworkBuilder(WritingAgent):
    async def run(self, request: FrameworkRequest, checkpoint: Checkpoint | None = None) -> FrameworkResponse:
        if self.skill.manifest.agent_type != "FRAMEWORK":
            raise AgentFailure("SKILL_AGENT_MISMATCH")
        result = await self._run(request, FrameworkResponse, checkpoint)
        assert isinstance(result, FrameworkResponse)
        return result
