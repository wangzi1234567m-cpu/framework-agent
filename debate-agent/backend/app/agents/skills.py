"""Load immutable, reviewed writing-method packages without executing their contents."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, ValidationError

from app.schemas.agent import FrameworkRequest, FrameworkResponse, TopicRequest, TopicResponse
from app.schemas.domain import Contract

STAGES = ("analyze", "draft", "review", "revise")
CONTRACTS = {
    "TOPIC": ("topic-analysis", "TopicRequest@1", "TopicResponse@1"),
    "FRAMEWORK": ("framework-building", "FrameworkRequest@1", "FrameworkResponse@1"),
}
SAFE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
SAFE_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class SkillError(ValueError):
    pass


class SkillManifest(Contract):
    contract_version: Literal[1]
    skill_id: str
    skill_version: str
    agent_type: Literal["TOPIC", "FRAMEWORK"]
    request_contract: str
    response_contract: str
    rule_set_version: str = Field(min_length=1)
    rule_ids: list[str]
    prompt_version: str = Field(min_length=1)
    stage_prompts: dict[str, str]
    source_sample_ids: list[str]
    submission_status: Literal["DRAFT"] = "DRAFT"


class PublishedSkill(Contract):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: UUID
    approved_at: AwareDatetime


@dataclass(frozen=True)
class SkillPack:
    manifest: SkillManifest
    instructions: str
    prompts: dict[str, str]
    sha256: str


def _read_package_file(root: Path, name: str) -> bytes:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise SkillError(f"unsafe or missing skill file: {name}")
    if path.stat().st_size > 128_000:
        raise SkillError(f"skill file too large: {name}")
    return path.read_bytes()


class SkillRegistry:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def selected(self, agent_type: str, *, allow_draft: bool = False) -> SkillPack:
        if agent_type not in CONTRACTS:
            raise SkillError("unknown agent type")
        skill_id = CONTRACTS[agent_type][0]
        if allow_draft:
            return self.load(agent_type, "0.1.0", allow_draft=True)
        try:
            registry = json.loads((self.root / "published.json").read_text(encoding="utf-8"))
            version = registry.get("active", {}).get(skill_id)
        except (OSError, json.JSONDecodeError) as exc:
            raise SkillError("approved skill registry is unavailable") from exc
        if not isinstance(version, str):
            raise SkillError("no approved active skill")
        return self.load(agent_type, version)

    def load(self, agent_type: str, version: str, *, allow_draft: bool = False) -> SkillPack:
        if agent_type not in CONTRACTS or not SAFE_VERSION.fullmatch(version):
            raise SkillError("unknown agent type or invalid skill version")
        skill_id, request_contract, response_contract = CONTRACTS[agent_type]
        if not SAFE_NAME.fullmatch(skill_id):
            raise SkillError("invalid skill identifier")
        folder = self.root / skill_id / version
        if not folder.resolve().is_relative_to(self.root):
            raise SkillError("skill package escapes registry root")
        try:
            manifest = SkillManifest.model_validate_json(_read_package_file(folder, "manifest.json"))
            if (manifest.skill_id, manifest.skill_version, manifest.agent_type) != (skill_id, version, agent_type):
                raise SkillError("skill manifest identity mismatch")
            if (manifest.request_contract, manifest.response_contract) != (request_contract, response_contract):
                raise SkillError("skill DTO contract mismatch")
            if set(manifest.stage_prompts) != set(STAGES):
                raise SkillError("skill must define four stage prompts")
            contents = {"manifest.json": _read_package_file(folder, "manifest.json")}
            contents["SKILL.md"] = _read_package_file(folder, "SKILL.md")
            contents["examples.json"] = _read_package_file(folder, "examples.json")
            examples = json.loads(contents["examples.json"])
            if not isinstance(examples, dict) or not isinstance(examples.get("cases"), list):
                raise SkillError("examples.json needs a cases array")
            request_type, response_type = (
                (TopicRequest, TopicResponse) if agent_type == "TOPIC" else (FrameworkRequest, FrameworkResponse)
            )
            good = bad = 0
            for case in examples["cases"]:
                if not isinstance(case, dict) or not case.get("review_note") or not isinstance(case.get("rule_ids"), list):
                    raise SkillError("each example needs rule_ids and a review note")
                if not set(case["rule_ids"]).issubset(manifest.rule_ids):
                    raise SkillError("example references an unknown rule")
                if "request" in case and "response" in case:
                    request_type.model_validate(case["request"])
                    response_type.model_validate(case["response"])
                    good += 1
                elif "invalid_response" in case and case.get("expected_error") == "CANDIDATE_SCHEMA_INVALID":
                    try:
                        response_type.model_validate(case["invalid_response"])
                    except ValidationError:
                        bad += 1
                    else:
                        raise SkillError("invalid example unexpectedly passes DTO validation")
                else:
                    raise SkillError("example must include a valid pair or a rejected response")
            if not good or not bad:
                raise SkillError("skill package needs valid and invalid synthetic examples")
            prompts = {}
            for stage in STAGES:
                name = manifest.stage_prompts[stage]
                if not name.startswith("prompts/") or not name.endswith(".md"):
                    raise SkillError("stage prompts must be Markdown files in prompts/")
                contents[name] = _read_package_file(folder, name)
                prompts[stage] = contents[name].decode("utf-8")
            digest = hashlib.sha256()
            for name, content in sorted(contents.items()):
                digest.update(name.encode("utf-8") + b"\0" + content + b"\0")
            fingerprint = digest.hexdigest()
            if not allow_draft:
                registry = json.loads((self.root / "published.json").read_text(encoding="utf-8"))
                approval = registry.get("skills", {}).get(skill_id, {}).get(version)
                if approval is None or PublishedSkill.model_validate(approval).sha256 != fingerprint:
                    raise SkillError("skill version is not approved or its contents changed")
            return SkillPack(
                manifest=manifest,
                instructions=contents["SKILL.md"].decode("utf-8"),
                prompts=prompts,
                sha256=fingerprint,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise SkillError("skill package is incomplete or invalid") from exc


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate and inspect a local Skill package")
    parser.add_argument("agent_type", choices=tuple(CONTRACTS))
    parser.add_argument("version")
    parser.add_argument("--published", action="store_true", help="Require reviewed allowlist entry")
    arguments = parser.parse_args()
    package = SkillRegistry(Path(__file__).resolve().parents[2] / "knowledge" / "skills").load(
        arguments.agent_type, arguments.version, allow_draft=not arguments.published,
    )
    print(json.dumps({
        "skill_id": package.manifest.skill_id, "version": package.manifest.skill_version,
        "sha256": package.sha256, "approved": arguments.published,
    }, ensure_ascii=False))
