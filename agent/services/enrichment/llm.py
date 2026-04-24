"""OpenRouter-backed JSON synthesis for enrichment briefs."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from agent.config.settings import Settings
from agent.services.observability.events import log_processing_step, log_trace_event
from agent.services.observability.langfuse_llm import (
    langfuse_openrouter_generation,
    update_langfuse_generation_success,
)


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

    def _log_token_usage(
        self,
        *,
        usage: dict[str, Any] | None,
        purpose: str,
        trace_id: str | None,
        lead_id: str | None,
    ) -> None:
        if not isinstance(usage, dict):
            return
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        tid = trace_id or "trace_llm"
        log_processing_step(
            component="openrouter",
            step="llm.tokens",
            message="OpenRouter token usage",
            trace_id=tid,
            lead_id=lead_id,
            purpose=purpose,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=self._settings.openrouter_model,
        )
        log_trace_event(
            event_type="llm_token_usage",
            trace_id=tid,
            lead_id=lead_id,
            status="ok",
            payload={
                "purpose": purpose,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "model": self._settings.openrouter_model,
            },
        )

    async def generate_model(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        response_model: type[BaseModel],
        trace_id: str | None = None,
        lead_id: str | None = None,
        purpose: str = "openrouter.json",
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
            with langfuse_openrouter_generation(
                self._settings,
                trace_id=trace_id,
                lead_id=lead_id,
                purpose=purpose,
                model=self._settings.openrouter_model,
            ) as lf_obs:
                response = await self._post(payload=payload)
                response.raise_for_status()
                raw = response.json()
                self._log_token_usage(
                    usage=raw.get("usage") if isinstance(raw, dict) else None,
                    purpose=purpose,
                    trace_id=trace_id,
                    lead_id=lead_id,
                )
                content = raw["choices"][0]["message"]["content"]
                data = json.loads(content)
                validated = response_model.model_validate(data)
                update_langfuse_generation_success(
                    lf_obs,
                    parsed_output=data,
                    usage=raw.get("usage") if isinstance(raw, dict) else None,
                )
                return validated
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
