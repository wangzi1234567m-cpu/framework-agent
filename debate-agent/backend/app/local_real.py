"""Explicit single-user localhost workbench, not a production authentication bypass."""

import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from app.demo import create_demo_app
from app.experiments import RecordedModel
from app.infrastructure.llm.openai_compatible import OpenAICompatibleModel, output_budget

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
STATE = Path(os.environ["LOCALAPPDATA"]) / "DebateAgent" / "workbench"


class LocalRecordedModel(RecordedModel):
    def __init__(self, kind):
        super().__init__(OpenAICompatibleModel(temperature=0, max_tokens=output_budget(kind)), kind)
        self.model = self.inner.model
        self.trace_id = uuid4().hex

    async def complete(self, stage, instructions, payload):
        try:
            return await super().complete(stage, instructions, payload)
        finally:
            folder = STATE / "traces"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{self.trace_id}.json").write_text(json.dumps({
                "model": self.model, "kind": self.kind, "max_tokens": self.inner.max_tokens,
                "calls": self.calls,
            }, ensure_ascii=False, indent=2), encoding="utf-8")


app = create_demo_app(real=True, database_path=STATE / "workbench.sqlite", model_factory=LocalRecordedModel)
