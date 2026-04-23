"""HubSpot MCP client wrapper."""

from __future__ import annotations

from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.common.schemas import ErrorEnvelope
from agent.services.crm.schemas import CRMBookingPayload, CRMEnrichmentPayload, CRMLeadPayload, CRMWriteResult
from agent.services.observability.events import log_trace_event
from agent.services.policy.outbound_policy import OutboundPolicyService


class HubSpotMCPService:
    # Implements: FR-12
    # Workflow: crm_sync.md
    # Schema: crm_event.md
    # API: crm_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        policy_service: OutboundPolicyService,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int = 2,
    ) -> None:
        self._settings = settings
        self._policy_service = policy_service
        self._http_client = http_client
        self._max_retries = max_retries

    async def upsert_contact(
        self,
        *,
        contact: CRMLeadPayload,
        trace_id: str,
        idempotency_key: str,
    ) -> CRMWriteResult:
        payload = {"lead": contact.model_dump(mode="json")}
        return await self._write(
            endpoint="/crm/lead",
            payload=payload,
            trace_id=trace_id,
            lead_id=contact.lead_id,
            idempotency_key=idempotency_key,
            success_status="upserted",
        )

    async def append_enrichment(
        self,
        *,
        lead_id: str,
        enrichment: CRMEnrichmentPayload,
        trace_id: str,
        idempotency_key: str,
    ) -> CRMWriteResult:
        payload = {
            "lead_id": lead_id,
            "event_type": "enrichment_updated",
            "event_key": idempotency_key,
            "payload": enrichment.model_dump(mode="json"),
        }
        return await self._write(
            endpoint="/crm/event",
            payload=payload,
            trace_id=trace_id,
            lead_id=lead_id,
            idempotency_key=idempotency_key,
            success_status="event_recorded",
        )

    async def record_booking(
        self,
        *,
        lead_id: str,
        booking: CRMBookingPayload,
        trace_id: str,
        idempotency_key: str,
    ) -> CRMWriteResult:
        payload = {
            "lead_id": lead_id,
            "event_type": "booking_confirmed",
            "event_key": idempotency_key,
            "payload": booking.model_dump(mode="json"),
        }
        return await self._write(
            endpoint="/crm/event",
            payload=payload,
            trace_id=trace_id,
            lead_id=lead_id,
            idempotency_key=idempotency_key,
            success_status="event_recorded",
        )

    async def _write(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        trace_id: str,
        lead_id: str,
        idempotency_key: str,
        success_status: str,
    ) -> CRMWriteResult:
        self._settings.require("hubspot_mcp_base_url", "hubspot_mcp_api_key")
        decisions = self._policy_service.check_email_send(trace_id=trace_id, lead_id=lead_id)
        blocked = next((decision for decision in decisions if not decision.is_allowed), None)
        if blocked:
            error = ErrorEnvelope(
                error_code="POLICY_BLOCKED",
                error_message=blocked.reason,
                retryable=False,
                details={"policy_type": blocked.policy_type},
            )
            return CRMWriteResult(status="blocked", lead_id=lead_id, error=error)

        url = f"{self._settings.hubspot_mcp_base_url.rstrip('/')}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self._settings.hubspot_mcp_api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }

        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._post(url=url, headers=headers, json=payload)
                raw = self._safe_json(response)
                if response.is_success:
                    result = CRMWriteResult(
                        status=success_status,
                        lead_id=lead_id,
                        record_id=self._coerce_str(raw.get("record_id") or raw.get("crm_record_id")),
                        event_id=self._coerce_str(raw.get("event_id") or raw.get("crm_event_id")),
                        raw_response=raw,
                    )
                    log_trace_event(
                        event_type="crm_write_succeeded",
                        trace_id=trace_id,
                        lead_id=lead_id,
                        status="success",
                        payload={"endpoint": endpoint},
                    )
                    return result

                retryable = response.status_code >= 500
                if retryable and attempt <= self._max_retries:
                    continue
                error = ErrorEnvelope(
                    error_code="CRM_SYNC_FAILED",
                    error_message=f"HubSpot MCP returned HTTP {response.status_code}",
                    retryable=retryable,
                    details={"endpoint": endpoint, "response": raw, "attempt": attempt},
                )
                return CRMWriteResult(status="failed", lead_id=lead_id, error=error, raw_response=raw)
            except httpx.TimeoutException as exc:
                if attempt <= self._max_retries:
                    continue
                return CRMWriteResult(
                    status="failed",
                    lead_id=lead_id,
                    error=ErrorEnvelope(error_code="TOOL_TIMEOUT", error_message=str(exc), retryable=True),
                )
            except httpx.HTTPError as exc:
                if attempt <= self._max_retries:
                    continue
                return CRMWriteResult(
                    status="failed",
                    lead_id=lead_id,
                    error=ErrorEnvelope(error_code="SOURCE_UNAVAILABLE", error_message=str(exc), retryable=True),
                )

    async def _post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(url, headers=headers, json=json)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.post(url, headers=headers, json=json)

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            parsed = response.json()
            return parsed if isinstance(parsed, dict) else {"payload": parsed}
        except ValueError:
            return {}

    @staticmethod
    def _coerce_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def map_enrichment_to_crm_payload(*, lead_id: str, enrichment_artifact: dict[str, Any]) -> CRMEnrichmentPayload:
    """Map normalized enrichment artifact into CRM enrichment fields."""
    signals = enrichment_artifact.get("signals", {}) if isinstance(enrichment_artifact, dict) else {}

    def summary(path: str) -> str | None:
        signal = signals.get(path)
        if not isinstance(signal, dict):
            return None
        raw_summary = signal.get("summary")
        if isinstance(raw_summary, dict):
            return str(raw_summary)
        if isinstance(raw_summary, str):
            return raw_summary
        return None

    return CRMEnrichmentPayload(
        lead_id=lead_id,
        funding_signal_summary=summary("crunchbase"),
        job_velocity_summary=summary("job_posts"),
        layoffs_signal_summary=summary("layoffs"),
        leadership_signal_summary=summary("leadership_changes"),
        bench_match_status=enrichment_artifact.get("bench_match_status"),
        brief_references=list(enrichment_artifact.get("brief_references", [])),
        raw=enrichment_artifact,
    )

