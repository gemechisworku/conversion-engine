"""Africa's Talking webhook parsing."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from agent.config.settings import Settings
from agent.services.common.schemas import ErrorEnvelope
from agent.services.sms.schemas import InboundSMSEvent


class AfricasTalkingWebhookParser:
    # Implements: FR-9, FR-10, FR-15
    # Workflow: reply_handling.md
    # Schema: conversation_state.md
    # API: orchestration_api.md
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def parse(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None,
        raw_body: bytes | str | None = None,
    ) -> InboundSMSEvent:
        try:
            normalized_headers = {k.lower(): v for k, v in (headers or {}).items()}
            if not self._validate_signature(payload, normalized_headers, raw_body):
                return self._malformed_event(payload, "Webhook signature validation failed.", "PERMISSION_DENIED")

            event_type_raw = str(payload.get("eventType") or payload.get("event_type") or "").strip().lower()
            if event_type_raw in ("delivery_report", "delivery", "delivery-report"):
                event_type = "delivery_report"
            elif payload.get("text") or payload.get("message") or payload.get("content"):
                event_type = "inbound_sms"
            elif not event_type_raw:
                return self._malformed_event(payload, "Webhook payload is missing event type and message content.")
            else:
                event_type = "unknown"

            from_number = self._coerce(payload.get("from") or payload.get("fromNumber"))
            to_number = self._coerce(payload.get("to") or payload.get("toNumber"))
            text = self._coerce(payload.get("text") or payload.get("message") or payload.get("content"))
            message_id = self._coerce(payload.get("id") or payload.get("messageId") or payload.get("message_id"))
            received_at = self._coerce_datetime(payload.get("date") or payload.get("createdAt"))
            if text:
                normalized_text = text.strip().upper()
                if normalized_text == "STOP":
                    event_type = "command_stop"
                elif normalized_text == "HELP":
                    event_type = "command_help"
                elif normalized_text == "UNSUB":
                    event_type = "command_unsub"
            if event_type == "inbound_sms" and (not from_number or not to_number or not text):
                return self._malformed_event(payload, "Inbound SMS payload missing from/to/text.")

            return InboundSMSEvent(
                event_type=event_type,
                provider_message_id=message_id,
                from_number=from_number,
                to_number=to_number,
                text=text,
                received_at=received_at,
                raw_payload_ref=self._payload_ref(payload),
                raw_payload=payload,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            return self._malformed_event(payload, f"Unhandled SMS webhook parsing error: {exc}")

    def _validate_signature(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        raw_body: bytes | str | None,
    ) -> bool:
        if not self._settings.africastalking_webhook_secret:
            return True
        # SPEC-GAP: Africa's Talking signature header is not documented in repo specs.
        provided = headers.get("x-webhook-signature", "")
        if not provided:
            return False
        if isinstance(raw_body, bytes):
            body_bytes = raw_body
        elif isinstance(raw_body, str):
            body_bytes = raw_body.encode("utf-8")
        else:
            body_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        computed = hmac.new(
            self._settings.africastalking_webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(provided, computed)

    def _malformed_event(
        self,
        payload: dict[str, Any],
        message: str,
        error_code: str = "INVALID_INPUT",
    ) -> InboundSMSEvent:
        return InboundSMSEvent(
            event_type="malformed",
            raw_payload_ref=self._payload_ref(payload),
            error=ErrorEnvelope(error_code=error_code, error_message=message, retryable=False),
            raw_payload=payload,
        )

    @staticmethod
    def _payload_ref(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _coerce(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            cleaned = value.strip().replace("Z", "+00:00")
            if cleaned:
                try:
                    return datetime.fromisoformat(cleaned)
                except ValueError:
                    pass
        return datetime.now(UTC)
