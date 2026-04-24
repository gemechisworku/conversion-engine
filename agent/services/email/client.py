"""Outbound Resend client and combined email service."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.common.schemas import ErrorEnvelope, ProviderSendResult
from agent.services.email.router import EmailEventRouter
from agent.services.email.schemas import InboundEmailEvent, OutboundEmailRequest
from agent.services.email.webhook import ResendWebhookParser
from agent.services.observability.events import log_trace_event
from agent.services.policy.outbound_policy import OutboundPolicyService

LOGGER = logging.getLogger("agent.services.email")


class ResendEmailClient:
    # Implements: FR-7, FR-8, FR-9, FR-10, FR-15, FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: outreach_draft.md
    # API: outreach_api.md
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

    async def send_email(self, request: OutboundEmailRequest) -> ProviderSendResult:
        self._settings.require("resend_api_key")
        metadata = request.metadata or {}
        policy_decisions = self._policy_service.check_email_send(
            trace_id=request.trace_id,
            lead_id=request.lead_id,
        )
        policy_decisions.append(
            self._policy_service.check_review_approval(
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                review_id=request.review_id,
                review_status=request.review_status,
            )
        )
        policy_decisions.append(
            self._policy_service.check_claim_grounding(
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                unsupported_claims=bool(metadata.get("unsupported_claims", False)),
            )
        )
        combined_body = f"{request.subject}\n{request.text_body or ''}\n{request.html_body or ''}"
        policy_decisions.append(
            self._policy_service.check_bench_commitment(
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                message=combined_body,
                bench_verified=bool(metadata.get("bench_verified", False)),
            )
        )
        blocked = next((decision for decision in policy_decisions if not decision.is_allowed), None)
        if blocked:
            error = ErrorEnvelope(
                error_code="POLICY_BLOCKED",
                error_message=blocked.reason,
                retryable=False,
                details={"policy_type": blocked.policy_type},
            )
            log_trace_event(
                event_type="email_send_blocked",
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                status="blocked",
                payload={"draft_id": request.draft_id},
                error=error.model_dump(),
            )
            return ProviderSendResult(
                provider="resend",
                provider_message_id=None,
                accepted=False,
                raw_status="blocked",
                error=error,
            )

        payload: dict[str, Any] = {
            "from": request.from_email or self._settings.resend_from_email,
            "to": [request.to_email],
            "subject": request.subject,
            "headers": {
                "X-Lead-Id": request.lead_id,
                "X-Draft-Id": request.draft_id,
                "X-Tenacious-Status": str(metadata.get("tenacious_status", "draft")),
            },
        }
        if not payload["from"]:
            error = ErrorEnvelope(
                error_code="INVALID_INPUT",
                error_message="Missing sender email. Provide request.from_email or RESEND_FROM_EMAIL.",
                retryable=False,
            )
            return ProviderSendResult(
                provider="resend",
                provider_message_id=None,
                accepted=False,
                raw_status="failed",
                error=error,
            )
        if request.text_body:
            payload["text"] = request.text_body
        if request.html_body:
            payload["html"] = request.html_body

        headers = {
            "Authorization": f"Bearer {self._settings.resend_api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": request.idempotency_key,
        }
        url = f"{self._settings.resend_api_url.rstrip('/')}/emails"

        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._post(url=url, headers=headers, json=payload)
                raw_response = self._safe_json(response)
                if response.is_success:
                    provider_message_id = str(raw_response.get("id", "")).strip() or None
                    result = ProviderSendResult(
                        provider="resend",
                        provider_message_id=provider_message_id,
                        accepted=True,
                        raw_status="queued",
                        raw_response=raw_response,
                    )
                    log_trace_event(
                        event_type="email_send_succeeded",
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
                    error_message=f"Resend returned HTTP {response.status_code}.",
                    retryable=retryable,
                    details={"response": raw_response, "attempt": attempt},
                )
                log_trace_event(
                    event_type="email_send_failed",
                    trace_id=request.trace_id,
                    lead_id=request.lead_id,
                    status="failure",
                    payload={"draft_id": request.draft_id},
                    error=error.model_dump(),
                )
                return ProviderSendResult(
                    provider="resend",
                    provider_message_id=None,
                    accepted=False,
                    raw_status="failed",
                    error=error,
                    raw_response=raw_response,
                )
            except httpx.TimeoutException as exc:
                if attempt <= self._max_retries:
                    continue
                return self._transport_error(
                    request=request,
                    error_code="TOOL_TIMEOUT",
                    message=str(exc) or "Resend request timed out.",
                )
            except httpx.HTTPError as exc:
                if attempt <= self._max_retries:
                    continue
                return self._transport_error(
                    request=request,
                    error_code="SOURCE_UNAVAILABLE",
                    message=str(exc) or "Resend request failed.",
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

    def _transport_error(
        self,
        *,
        request: OutboundEmailRequest,
        error_code: str,
        message: str,
    ) -> ProviderSendResult:
        error = ErrorEnvelope(
            error_code=error_code,
            error_message=message,
            retryable=True,
        )
        log_trace_event(
            event_type="email_send_failed",
            trace_id=request.trace_id,
            lead_id=request.lead_id,
            status="failure",
            payload={"draft_id": request.draft_id},
            error=error.model_dump(),
        )
        LOGGER.warning("Email send failed: %s", message)
        return ProviderSendResult(
            provider="resend",
            provider_message_id=None,
            accepted=False,
            raw_status="failed",
            error=error,
        )

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {"payload": payload}
        except ValueError:
            return {}


class EmailService:
    """Facade that exposes send and webhook handling interfaces."""

    def __init__(
        self,
        *,
        client: ResendEmailClient,
        parser: ResendWebhookParser,
        router: EmailEventRouter,
    ) -> None:
        self._client = client
        self._parser = parser
        self._router = router

    async def send_email(self, request: OutboundEmailRequest) -> ProviderSendResult:
        return await self._client.send_email(request)

    async def handle_webhook(
        self,
        *,
        payload: dict[str, Any],
        headers: dict[str, str] | None,
        raw_body: bytes | str | None = None,
    ) -> InboundEmailEvent:
        event = self._parser.parse(payload=payload, headers=headers, raw_body=raw_body)
        await self._router.route(event)
        return event
