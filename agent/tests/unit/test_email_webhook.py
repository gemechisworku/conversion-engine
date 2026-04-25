from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from pathlib import Path

from agent.config.settings import Settings
from agent.services.email.client import EmailService, ResendEmailClient
from agent.services.email.router import EmailEventRouter
from agent.services.email.webhook import ResendWebhookParser
from agent.services.policy.outbound_policy import OutboundPolicyService


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "webhooks" / "resend"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "resend_api_key": "test_key",
        "resend_api_url": "https://api.resend.com",
        "resend_webhook_secret": "",
        "resend_webhook_signature_header": "resend-signature",
        "challenge_mode": False,
        "sink_routing_enabled": True,
        "kill_switch_enabled": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_reply_webhook_is_normalized() -> None:
    parser = ResendWebhookParser(_settings())
    payload = _load_fixture("reply_event.json")

    event = parser.parse(payload=payload, headers={})

    assert event.event_type == "reply"
    assert event.provider_message_id == "re_123"
    assert event.rfc_message_id == "<prospect-reply-abc@mail.example>"
    assert event.in_reply_to == "<outbound-ses-id@amazonses.com>"
    assert "first@id.com" in (event.references or "")
    assert event.from_email == "prospect@example.com"
    assert event.to_email == "outreach@tenacious.example"
    assert event.text_body == "Can we discuss next week?"


def test_bounce_webhook_is_normalized() -> None:
    parser = ResendWebhookParser(_settings())
    payload = _load_fixture("bounce_event.json")

    event = parser.parse(payload=payload, headers={})

    assert event.event_type == "bounce"
    assert event.provider_message_id == "re_124"


def test_malformed_webhook_returns_malformed_event() -> None:
    parser = ResendWebhookParser(_settings())
    payload = _load_fixture("malformed_event.json")

    event = parser.parse(payload=payload, headers={})

    assert event.event_type == "malformed"
    assert event.error is not None
    assert event.error.error_code == "INVALID_INPUT"


def test_service_routes_reply_event() -> None:
    parser = ResendWebhookParser(_settings())
    routed: list[str] = []

    async def on_reply(event: object) -> None:
        routed.append(event.event_type)

    router = EmailEventRouter(on_reply=on_reply)
    service = EmailService(
        client=ResendEmailClient(
            settings=_settings(),
            policy_service=OutboundPolicyService(_settings()),
        ),
        parser=parser,
        router=router,
    )

    payload = _load_fixture("reply_event.json")
    event = asyncio.run(service.handle_webhook(payload=payload, headers={}))

    assert event.event_type == "reply"
    assert routed == ["reply"]


def test_reply_webhook_without_body_is_still_valid_reply_event() -> None:
    parser = ResendWebhookParser(_settings())
    payload = {
        "type": "email.received",
        "data": {
            "id": "re_999",
            "email_id": "re_999",
            "message_id": "<msg-no-body@example.com>",
            "from": "prospect@example.com",
            "to": ["lead_x@chuairkoon.resend.app"],
            "subject": "Re: Intro",
        },
    }
    event = parser.parse(payload=payload, headers={})
    assert event.event_type == "reply"
    assert event.error is None


def test_reply_webhook_accepts_valid_svix_signature() -> None:
    signing_key_bytes = b"svix_test_secret_bytes_123"
    secret = "whsec_" + base64.b64encode(signing_key_bytes).decode("utf-8")
    settings = _settings(resend_webhook_secret=secret)
    parser = ResendWebhookParser(settings)
    payload = {
        "type": "email.received",
        "data": {
            "email_id": "re_777",
            "message_id": "<msg-svix@example.com>",
            "from": "prospect@example.com",
            "to": ["lead_abc@chuairkoon.resend.app"],
            "subject": "Re: Intro",
        },
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    svix_id = "msg_123"
    svix_ts = "1714042110"
    signed = f"{svix_id}.{svix_ts}.{raw}".encode("utf-8")
    sig = base64.b64encode(hmac.new(signing_key_bytes, signed, hashlib.sha256).digest()).decode("utf-8")
    headers = {
        "svix-id": svix_id,
        "svix-timestamp": svix_ts,
        "svix-signature": f"v1,{sig}",
    }
    event = parser.parse(payload=payload, headers=headers, raw_body=raw)
    assert event.event_type == "reply"
    assert event.error is None
