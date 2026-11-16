"""Optional OpenAI-compatible JSON transport; configuration is never hard-coded."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.agents.runtime import AgentFailure


class OpenAICompatibleModel:
    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")
        if not self.base_url.startswith("https://") or not self.api_key or not self.model:
            raise RuntimeError("LLM_BASE_URL (HTTPS), LLM_API_KEY and LLM_MODEL must be set")

    async def complete(self, stage: str, instructions: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions + "\nReply with one JSON object only."},
                {"role": "user", "content": json.dumps({"stage": stage, "data": payload}, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=40) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                value = json.loads(response.json()["choices"][0]["message"]["content"])
        except httpx.TimeoutException as exc:
            raise AgentFailure("LLM_TIMEOUT") from exc
        except httpx.HTTPStatusError as exc:
            code = "LLM_TRANSIENT" if exc.response.status_code == 429 or exc.response.status_code >= 500 else "LLM_RESPONSE_INVALID"
            raise AgentFailure(code) from exc
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise AgentFailure("LLM_RESPONSE_INVALID") from exc
        if not isinstance(value, dict):
            raise AgentFailure("LLM_RESPONSE_INVALID")
        return value
