"""Resend webhook parsing and normalization."""

from __future__ import annotations

import hashlib
import hmac
import json
import base64
from datetime import UTC, datetime
from typing import Any

from agent.config.settings import Settings
from agent.services.common.schemas import ErrorEnvelope
from agent.services.email.schemas import InboundEmailEvent


class ResendWebhookParser:
    # Implements: FR-9, FR-10, FR-15, FR-16
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
    ) -> InboundEmailEvent:
        try:
            normalized_headers = self._normalize_headers(headers)
            if not self._validate_signature(payload, normalized_headers, raw_body):
                return self._malformed_event(
                    payload=payload,
                    message="Webhook signature validation failed.",
                    error_code="PERMISSION_DENIED",
                )

            raw_event_type = self._extract_event_type(payload)
            if raw_event_type is None:
                return self._malformed_event(
                    payload=payload,
                    message="Webhook payload is missing event type.",
                )
            event_type = self._normalize_event_type(raw_event_type)
            raw_payload_ref = self._payload_ref(payload)
            provider_message_id, from_email, to_email, subject, text_body, html_body, received_at = (
                self._extract_core_fields(payload)
            )
            rfc_message_id, in_reply_to, references = self._extract_threading_fields(payload)

            return InboundEmailEvent(
                event_type=event_type,
                provider_message_id=provider_message_id,
                from_email=from_email,
                to_email=to_email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                received_at=received_at,
                rfc_message_id=rfc_message_id,
                in_reply_to=in_reply_to,
                references=references,
                raw_payload_ref=raw_payload_ref,
                raw_payload=payload,
            )
        except Exception as exc:  # pragma: no cover - defensive parser guard
            return self._malformed_event(
                payload=payload,
                message=f"Unhandled resend webhook parsing error: {exc}",
            )

    def _normalize_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        if not headers:
            return {}
        return {k.lower(): v for k, v in headers.items()}

    def _validate_signature(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        raw_body: bytes | str | None,
    ) -> bool:
        if not self._settings.resend_webhook_secret:
            return True

        if self._has_svix_headers(headers):
            return self._validate_svix_signature(headers=headers, raw_body=raw_body, payload=payload)

        signature_header = self._settings.resend_webhook_signature_header.lower()
        provided_signature = headers.get(signature_header, "")
        if not provided_signature:
            return False

        if isinstance(raw_body, bytes):
            body_bytes = raw_body
        elif isinstance(raw_body, str):
            body_bytes = raw_body.encode("utf-8")
        else:
            body_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

        computed = hmac.new(
            self._settings.resend_webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, provided_signature)

    @staticmethod
    def _has_svix_headers(headers: dict[str, str]) -> bool:
        return bool(headers.get("svix-id") and headers.get("svix-timestamp") and headers.get("svix-signature"))

    def _validate_svix_signature(
        self,
        *,
        headers: dict[str, str],
        raw_body: bytes | str | None,
        payload: dict[str, Any],
    ) -> bool:
        secret = (self._settings.resend_webhook_secret or "").strip()
        if secret.startswith("whsec_"):
            secret = secret[len("whsec_") :]
        try:
            key = base64.b64decode(secret)
        except Exception:
            return False
        svix_id = headers.get("svix-id", "")
        svix_timestamp = headers.get("svix-timestamp", "")
        svix_signature = headers.get("svix-signature", "")
        if isinstance(raw_body, bytes):
            body = raw_body.decode("utf-8")
        elif isinstance(raw_body, str):
            body = raw_body
        else:
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        signed_content = f"{svix_id}.{svix_timestamp}.{body}".encode("utf-8")
        expected = base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode("utf-8")
        candidates = []
        for chunk in svix_signature.split():
            if "," not in chunk:
                continue
            version, sig = chunk.split(",", 1)
            if version.strip() == "v1":
                candidates.append(sig.strip())
        return any(hmac.compare_digest(expected, candidate) for candidate in candidates)

    def _extract_event_type(self, payload: dict[str, Any]) -> str | None:
        event_type = payload.get("type") or payload.get("event") or payload.get("event_type")
        if event_type is None:
            return None
        return str(event_type).lower()

    def _normalize_event_type(
        self,
        raw_event_type: str,
    ) -> str:
        if any(token in raw_event_type for token in ("reply", "received", "inbound")):
            return "reply"
        if "bounce" in raw_event_type:
            return "bounce"
        if any(token in raw_event_type for token in ("delivery.failed", "delivery_failure", "failed")):
            return "delivery_failure"
        return "unknown"

    def _extract_core_fields(
        self,
        payload: dict[str, Any],
    ) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None, datetime]:
        data = payload.get("data")
        if not isinstance(data, dict):
            data = payload

        provider_message_id = self._coerce_str(data.get("email_id") or data.get("id") or payload.get("id"))
        from_email = self._coerce_email(
            data.get("from_email")
            or data.get("from")
            or self._nested(data, "email", "from")
        )
        to_email = self._coerce_email(
            data.get("to_email")
            or self._first(data.get("to"))
            or self._nested(data, "email", "to")
        )
        subject = self._coerce_str(data.get("subject") or self._nested(data, "email", "subject"))
        text_body = self._coerce_str(data.get("text") or data.get("text_body") or self._nested(data, "email", "text"))
        html_body = self._coerce_str(data.get("html") or data.get("html_body") or self._nested(data, "email", "html"))
        received_at_raw = (
            data.get("received_at")
            or data.get("created_at")
            or payload.get("created_at")
            or payload.get("timestamp")
        )
        received_at = self._coerce_datetime(received_at_raw)
        return provider_message_id, from_email, to_email, subject, text_body, html_body, received_at

    def _extract_threading_fields(self, payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        data = payload.get("data")
        if not isinstance(data, dict):
            data = payload
        rfc_message_id = self._coerce_str(
            data.get("message_id") or self._nested(data, "email", "message_id") or data.get("message-id")
        )
        in_reply_to = self._coerce_str(data.get("in_reply_to") or data.get("inReplyTo"))
        references = self._coerce_str(data.get("references"))
        headers = data.get("headers")
        if isinstance(headers, dict):
            for key, value in headers.items():
                lk = str(key).lower()
                if lk == "in-reply-to" and value and not in_reply_to:
                    in_reply_to = self._coerce_str(value)
                if lk == "references" and value and not references:
                    references = self._coerce_str(value)
                if lk == "message-id" and value and not rfc_message_id:
                    rfc_message_id = self._coerce_str(value)
        return rfc_message_id, in_reply_to, references

    def _payload_ref(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def _malformed_event(
        self,
        *,
        payload: dict[str, Any],
        message: str,
        error_code: str = "INVALID_INPUT",
    ) -> InboundEmailEvent:
        return InboundEmailEvent(
            event_type="malformed",
            raw_payload_ref=self._payload_ref(payload),
            error=ErrorEnvelope(
                error_code=error_code,
                error_message=message,
                retryable=False,
            ),
            raw_payload=payload,
        )

    @staticmethod
    def _nested(payload: dict[str, Any], *keys: str) -> Any:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _first(value: Any) -> Any:
        if isinstance(value, list) and value:
            return value[0]
        return value

    @staticmethod
    def _coerce_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _coerce_email(value: Any) -> str | None:
        text = ResendWebhookParser._coerce_str(value)
        if not text:
            return None
        return text

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            raw = value.strip().replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        return datetime.now(UTC)
