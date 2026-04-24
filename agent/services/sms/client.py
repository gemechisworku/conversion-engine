"""Outbound Africa's Talking client and SMS facade."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.common.schemas import ErrorEnvelope, ProviderSendResult
from agent.services.observability.events import log_trace_event
from agent.services.policy.channel_policy import can_use_sms
from agent.services.policy.outbound_policy import OutboundPolicyService
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.sms.router import SMSRouter
from agent.services.sms.schemas import InboundSMSEvent, OutboundSMSRequest
from agent.services.sms.webhook import AfricasTalkingWebhookParser

LOGGER = logging.getLogger("agent.services.sms")


class SMSService:
    # Implements: FR-9, FR-10, FR-15, FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: conversation_state.md
    # API: outreach_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        policy_service: OutboundPolicyService,
        parser: AfricasTalkingWebhookParser,
        router: SMSRouter,
        http_client: httpx.AsyncClient | None = None,
        state_repo: SQLiteStateRepository | None = None,
        max_retries: int = 2,
    ) -> None:
        self._settings = settings
        self._policy_service = policy_service
        self._parser = parser
        self._router = router
        self._http_client = http_client
        self._state_repo = state_repo
        self._max_retries = max_retries

    async def send_warm_lead_sms(self, request: OutboundSMSRequest) -> ProviderSendResult:
        self._settings.require("africastalking_username", "africastalking_api_key")
        metadata = request.metadata or {}
        decisions = self._policy_service.check_email_send(trace_id=request.trace_id, lead_id=request.lead_id)
        decisions.append(
            self._policy_service.check_review_approval(
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                review_id=request.review_id,
                review_status=request.review_status,
            )
        )
        decisions.append(
            self._policy_service.check_claim_grounding(
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                unsupported_claims=bool(metadata.get("unsupported_claims", False)),
            )
        )
        decisions.append(
            self._policy_service.check_bench_commitment(
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                message=request.message,
                bench_verified=bool(metadata.get("bench_verified", False)),
            )
        )
        channel_decision = can_use_sms(lead_state=request.lead_channel_state, trace_id=request.trace_id)
        decisions.append(channel_decision)
        if self._state_repo is not None and not self._state_repo.is_sms_allowed(lead_id=request.lead_id):
            decisions.append(
                self._policy_service.check_escalation_trigger(
                    trace_id=request.trace_id,
                    lead_id=request.lead_id,
                    needs_human_handoff=True,
                    reason="SMS blocked due to STOP/UNSUB consent state.",
                )
            )
        blocked = next((decision for decision in decisions if not decision.is_allowed), None)
        if blocked:
            error = ErrorEnvelope(
                error_code="POLICY_BLOCKED",
                error_message=blocked.reason,
                retryable=False,
                details={"policy_type": blocked.policy_type},
            )
            log_trace_event(
                event_type="sms_send_blocked",
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                status="blocked",
                payload={"draft_id": request.draft_id},
                error=error.model_dump(),
            )
            return ProviderSendResult(
                provider="africastalking",
                accepted=False,
                raw_status="blocked",
                error=error,
            )

        data = {
            "username": self._settings.africastalking_username,
            "to": request.to_number,
            "message": request.message,
        }
        sender = request.from_shortcode or self._settings.africastalking_shortcode
        if sender:
            data["from"] = sender

        headers = {
            "Accept": "application/json",
            "apiKey": self._settings.africastalking_api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Idempotency-Key": request.idempotency_key,
        }

        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._post(url=self._settings.africastalking_api_url, headers=headers, data=data)
                raw_response = self._safe_json(response)
                if response.is_success:
                    recipient = self._first_recipient(raw_response)
                    provider_message_id = str(recipient.get("messageId", "")).strip() or None
                    status_text = str(recipient.get("status", "queued"))
                    result = ProviderSendResult(
                        provider="africastalking",
                        provider_message_id=provider_message_id,
                        accepted=True,
                        raw_status=status_text,
                        raw_response=raw_response,
                    )
                    log_trace_event(
                        event_type="sms_send_succeeded",
                        trace_id=request.trace_id,
                        lead_id=request.lead_id,
                        status="success",
                        payload={"provider_message_id": provider_message_id, "draft_id": request.draft_id},
                    )
                    if self._state_repo is not None:
                        self._state_repo.bind_phone(lead_id=request.lead_id, phone_number=request.to_number)
                    return result

                retryable = response.status_code >= 500
                if retryable and attempt <= self._max_retries:
                    continue
                error = ErrorEnvelope(
                    error_code="DELIVERY_FAILED",
                    error_message=f"Africa's Talking returned HTTP {response.status_code}.",
                    retryable=retryable,
                    details={"response": raw_response, "attempt": attempt},
                )
                log_trace_event(
                    event_type="sms_send_failed",
                    trace_id=request.trace_id,
                    lead_id=request.lead_id,
                    status="failure",
                    payload={"draft_id": request.draft_id},
                    error=error.model_dump(),
                )
                return ProviderSendResult(
                    provider="africastalking",
                    accepted=False,
                    raw_status="failed",
                    error=error,
                    raw_response=raw_response,
                )
            except httpx.TimeoutException as exc:
                if attempt <= self._max_retries:
                    continue
                return self._transport_error(request, "TOOL_TIMEOUT", str(exc) or "SMS send timed out.")
            except httpx.HTTPError as exc:
                if attempt <= self._max_retries:
                    continue
                return self._transport_error(request, "SOURCE_UNAVAILABLE", str(exc) or "SMS send failed.")

    async def handle_inbound_sms(
        self,
        *,
        payload: dict[str, Any],
        headers: dict[str, str] | None,
        raw_body: bytes | str | None = None,
        lead_id: str | None = None,
    ) -> InboundSMSEvent:
        event = self._parser.parse(payload=payload, headers=headers, raw_body=raw_body)
        if self._state_repo is not None:
            resolved_lead_id = lead_id or self._state_repo.find_lead_by_phone(phone_number=event.from_number)
            if resolved_lead_id:
                if event.event_type in {"command_stop", "command_unsub"}:
                    self._state_repo.set_sms_consent(lead_id=resolved_lead_id, allowed=False)
                elif event.event_type == "command_help":
                    # Keep explicit consent as-is; help is informational.
                    pass
                if event.from_number:
                    self._state_repo.bind_phone(lead_id=resolved_lead_id, phone_number=event.from_number)
        await self._router.route(event)
        return event

    async def _post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        data: dict[str, str],
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(url, headers=headers, data=data)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.post(url, headers=headers, data=data)

    def _transport_error(self, request: OutboundSMSRequest, code: str, message: str) -> ProviderSendResult:
        error = ErrorEnvelope(error_code=code, error_message=message, retryable=True)
        log_trace_event(
            event_type="sms_send_failed",
            trace_id=request.trace_id,
            lead_id=request.lead_id,
            status="failure",
            payload={"draft_id": request.draft_id},
            error=error.model_dump(),
        )
        LOGGER.warning("SMS send failed: %s", message)
        return ProviderSendResult(
            provider="africastalking",
            accepted=False,
            raw_status="failed",
            error=error,
        )

    @staticmethod
    def _first_recipient(raw_response: dict[str, Any]) -> dict[str, Any]:
        sms_data = raw_response.get("SMSMessageData")
        if not isinstance(sms_data, dict):
            return {}
        recipients = sms_data.get("Recipients")
        if isinstance(recipients, list) and recipients:
            first = recipients[0]
            if isinstance(first, dict):
                return first
        return {}

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            parsed = response.json()
            return parsed if isinstance(parsed, dict) else {"payload": parsed}
        except ValueError:
            return {}
