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
        max_retries: int = 2,
    ) -> None:
        self._settings = settings
        self._policy_service = policy_service
        self._parser = parser
        self._router = router
        self._http_client = http_client
        self._max_retries = max_retries

    async def send_warm_lead_sms(self, request: OutboundSMSRequest) -> ProviderSendResult:
        self._settings.require("africastalking_username", "africastalking_api_key")
        decisions = self._policy_service.check_email_send(trace_id=request.trace_id, lead_id=request.lead_id)
        channel_decision = can_use_sms(lead_state=request.lead_channel_state, trace_id=request.trace_id)
        decisions.append(channel_decision)
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
    ) -> InboundSMSEvent:
        event = self._parser.parse(payload=payload, headers=headers, raw_body=raw_body)
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
