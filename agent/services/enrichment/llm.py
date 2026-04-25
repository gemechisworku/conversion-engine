"""OpenRouter-backed JSON synthesis for enrichment briefs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

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

    def _safe_slug(self, value: str) -> str:
        chars = []
        for c in value.lower():
            if c.isalnum():
                chars.append(c)
            elif c in {"-", "_"}:
                chars.append(c)
            else:
                chars.append("_")
        slug = "".join(chars).strip("_")
        return slug[:80] or "openrouter_json"

    def _write_call_log(
        self,
        *,
        call_id: str,
        purpose: str,
        trace_id: str | None,
        lead_id: str | None,
        request_payload: dict[str, Any],
        status: str,
        response_status_code: int | None = None,
        response_body: dict[str, Any] | str | None = None,
        parsed_output: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        started = started_at or datetime.now(UTC)
        finished = datetime.now(UTC)
        record = {
            "call_id": call_id,
            "provider": "openrouter",
            "purpose": purpose,
            "status": status,
            "trace_id": trace_id,
            "lead_id": lead_id,
            "model": self._settings.openrouter_model,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "elapsed_ms": round((finished - started).total_seconds() * 1000, 2),
            "request": request_payload,
            "response_status_code": response_status_code,
            "response_body": response_body,
            "parsed_output": parsed_output,
            "token_usage": {
                "prompt_tokens": int((usage or {}).get("prompt_tokens") or 0),
                "completion_tokens": int((usage or {}).get("completion_tokens") or 0),
                "total_tokens": int((usage or {}).get("total_tokens") or 0),
                "raw": usage or {},
            },
            "error": error,
        }
        log_dir = Path(self._settings.llm_call_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = started.strftime("%Y%m%dT%H%M%S_%fZ")
        file_name = f"{stamp}_{self._safe_slug(purpose)}_{call_id[:8]}.json"
        (log_dir / file_name).write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

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
        call_id = uuid4().hex
        started_at = datetime.now(UTC)
        if not self.configured:
            self._write_call_log(
                call_id=call_id,
                purpose=purpose,
                trace_id=trace_id,
                lead_id=lead_id,
                request_payload={
                    "system_prompt": system_prompt,
                    "user_payload": user_payload,
                    "response_model": response_model.__name__,
                    "openrouter_url": self._settings.openrouter_api_url,
                },
                status="skipped_not_configured",
                error="openrouter_api_key is empty",
                started_at=started_at,
            )
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
        request_log_payload = {
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "response_model": response_model.__name__,
            "openrouter_payload": payload,
            "openrouter_url": self._settings.openrouter_api_url,
        }
        response_status_code: int | None = None
        response_body: dict[str, Any] | str | None = None
        usage_for_log: dict[str, Any] | None = None
        try:
            with langfuse_openrouter_generation(
                self._settings,
                trace_id=trace_id,
                lead_id=lead_id,
                purpose=purpose,
                model=self._settings.openrouter_model,
            ) as lf_obs:
                response = await self._post(payload=payload)
                response_status_code = response.status_code
                response.raise_for_status()
                raw = response.json()
                response_body = raw if isinstance(raw, dict) else str(raw)
                usage = raw.get("usage") if isinstance(raw, dict) else None
                usage_for_log = usage if isinstance(usage, dict) else None
                self._log_token_usage(
                    usage=usage,
                    purpose=purpose,
                    trace_id=trace_id,
                    lead_id=lead_id,
                )
                content = raw["choices"][0]["message"]["content"]
                data = json.loads(content)
                validated = response_model.model_validate(data)
                self._write_call_log(
                    call_id=call_id,
                    purpose=purpose,
                    trace_id=trace_id,
                    lead_id=lead_id,
                    request_payload=request_log_payload,
                    status="success",
                    response_status_code=response_status_code,
                    response_body=response_body,
                    parsed_output=data,
                    usage=usage_for_log,
                    started_at=started_at,
                )
                update_langfuse_generation_success(
                    lf_obs,
                    parsed_output=data,
                    usage=usage,
                )
                return validated
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                response_status_code = exc.response.status_code
                response_body = exc.response.text
            self._write_call_log(
                call_id=call_id,
                purpose=purpose,
                trace_id=trace_id,
                lead_id=lead_id,
                request_payload=request_log_payload,
                status="error",
                response_status_code=response_status_code,
                response_body=response_body,
                usage=usage_for_log,
                error=f"{type(exc).__name__}: {exc}",
                started_at=started_at,
            )
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
