"""Run one or all currently queued jobs: python -m app.workflow.main [--drain]."""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
from pathlib import Path

from app.agents.skills import SkillRegistry
from app.core.database import session_factory
from app.infrastructure.llm.openai_compatible import OpenAICompatibleModel, output_budget
from app.workflow.runner import JobRunner


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drain", action="store_true", help="Process queued jobs until none remain")
    args = parser.parse_args()
    worker = JobRunner(
        session_factory(),
        SkillRegistry(Path(__file__).resolve().parents[2] / "knowledge" / "skills"),
        lambda kind: OpenAICompatibleModel(max_tokens=output_budget(kind)),
        f"{socket.gethostname()}-{os.getpid()}",
    )
    while await worker.run_once():
        if not args.drain:
            break


if __name__ == "__main__":
    asyncio.run(main())
