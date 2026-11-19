"""Optional OpenAI-compatible JSON transport; configuration is never hard-coded."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.agents.runtime import AgentFailure


def output_budget(kind: str) -> int:
    default = "16384" if kind == "TOPIC" else "32768"
    value = int(os.getenv(f"LLM_{kind}_MAX_TOKENS", default))
    if value < 1:
        raise ValueError("output token budget must be positive")
    return value


class OpenAICompatibleModel:
    def __init__(self, *, temperature: float | None = None, max_tokens: int | None = None) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")
        self.temperature = temperature
        self.max_tokens = max_tokens if max_tokens is not None else output_budget("FRAMEWORK")
        self.timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "150"))
        self.last_usage: dict[str, Any] | None = None
        self.last_completion: dict[str, Any] | None = None
        if not self.base_url.startswith("https://") or not self.api_key or not self.model:
            raise RuntimeError("LLM_BASE_URL (HTTPS), LLM_API_KEY and LLM_MODEL must be set")

    async def complete(self, stage: str, instructions: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_usage = None
        self.last_completion = None
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions + "\nReply with one JSON object only."},
                {"role": "user", "content": json.dumps({"stage": stage, "data": payload}, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                document = response.json()
                self.last_usage = document.get("usage")
                choice = document["choices"][0]
                content = choice["message"]["content"]
                # Keep malformed model content for private diagnostics, never headers or keys.
                self.last_completion = {"content": content, "finish_reason": choice.get("finish_reason")}
                if choice.get("finish_reason") == "length":
                    raise AgentFailure("LLM_OUTPUT_TRUNCATED")
                value = json.loads(content)
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
