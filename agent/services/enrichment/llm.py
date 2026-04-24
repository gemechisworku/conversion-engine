"""OpenRouter-backed JSON synthesis for enrichment briefs."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from agent.config.settings import Settings


class OpenRouterJSONClient:
    # Implements: FR-3, FR-4, FR-6
    # Workflow: lead_intake_and_enrichment.md
    # Schema: ai_maturity_score.md, hiring_signal_brief.md, competitor_gap_brief.md
    # API: scoring_api.md
    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    @property
    def configured(self) -> bool:
        return bool(self._settings.openrouter_api_key.strip())

    async def generate_model(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        response_model: type[BaseModel],
    ) -> BaseModel | None:
        if not self.configured:
            return None
        payload = {
            "model": self._settings.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n"
                        "Return only valid JSON. Do not include markdown. "
                        "Do not invent evidence; use only supplied evidence_refs and source summaries."
                    ),
                },
                {"role": "user", "content": json.dumps(user_payload, default=str)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        try:
            response = await self._post(payload=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            return response_model.model_validate(data)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError):
            return None

    async def _post(self, *, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost/conversion-engine",
            "X-Title": "Tenacious Conversion Engine",
        }
        if self._http_client is not None:
            return await self._http_client.post(
                self._settings.openrouter_api_url,
                json=payload,
                headers=headers,
                timeout=self._settings.http_timeout_seconds,
            )
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.post(self._settings.openrouter_api_url, json=payload, headers=headers)
