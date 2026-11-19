"""Deterministic synthetic responses for local UI and experiment plumbing only."""

from __future__ import annotations

import copy
import json
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "skills"


def synthetic_pair(kind: str) -> dict:
    skill_id = {"TOPIC": "topic-analysis", "FRAMEWORK": "framework-building"}[kind]
    examples = json.loads((SKILL_ROOT / skill_id / "0.1.0" / "examples.json").read_text(encoding="utf-8"))
    return copy.deepcopy(next(case for case in examples["cases"] if "response" in case))


class SyntheticModel:
    model = "mock-v1"

    def __init__(self, kind: str):
        self.kind = kind
        self.calls: list[str] = []

    async def complete(self, stage: str, instructions: str, payload: dict) -> dict:
        self.calls.append(stage)
        if stage == "analyze":
            return {"summary": "Synthetic fixture, not analysis of a new motion."}
        if stage == "review":
            return {"findings": []}
        return synthetic_pair(self.kind)["response"]
