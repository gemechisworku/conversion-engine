from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from agent.config.settings import Settings
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.policy.outbound_policy import OutboundPolicyService
from agent.services.sms.client import SMSService
from agent.services.sms.router import SMSRouter
from agent.services.sms.webhook import AfricasTalkingWebhookParser


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "webhooks" / "africastalking"


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "africastalking_username": "sandbox",
        "africastalking_api_key": "at_key",
        "africastalking_webhook_secret": "",
        "challenge_mode": False,
        "sink_routing_enabled": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_inbound_sms_parsed_successfully() -> None:
    parser = AfricasTalkingWebhookParser(_settings())
    event = parser.parse(payload=_load("inbound_sms.json"), headers={})
    assert event.event_type == "inbound_sms"
    assert event.from_number == "+254700000001"
    assert event.text == "Can we schedule for Tuesday?"


def test_malformed_sms_payload_handled() -> None:
    parser = AfricasTalkingWebhookParser(_settings())
    event = parser.parse(payload=_load("malformed_sms.json"), headers={})
    assert event.event_type == "malformed"
    assert event.error is not None


def test_inbound_sms_routed_downstream() -> None:
    routed: list[str] = []

    async def on_inbound(event) -> None:
        routed.append(event.event_type)

    settings = _settings()
    router = SMSRouter(on_inbound_sms=on_inbound)
    service = SMSService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        parser=AfricasTalkingWebhookParser(settings),
        router=router,
    )

    event = asyncio.run(service.handle_inbound_sms(payload=_load("inbound_sms.json"), headers={}))

    assert event.event_type == "inbound_sms"
    assert routed == ["inbound_sms"]


def test_sms_stop_command_parsed() -> None:
    parser = AfricasTalkingWebhookParser(_settings())
    event = parser.parse(
        payload={
            "id": "ATXid_stop",
            "from": "+254700000001",
            "to": "+254700000999",
            "text": "STOP",
            "date": "2026-04-23T12:30:00Z",
        },
        headers={},
    )
    assert event.event_type == "command_stop"


def test_stop_command_updates_sms_consent_state() -> None:
    settings = _settings()
    db_path = Path(f"outputs/test_sms_webhook_state_{uuid4().hex}.db")
    repo = SQLiteStateRepository(db_path=str(db_path))
    repo.set_sms_consent(lead_id="lead_sms_cmd", allowed=True)

    service = SMSService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        parser=AfricasTalkingWebhookParser(settings),
        router=SMSRouter(),
        state_repo=repo,
    )

    event = asyncio.run(
        service.handle_inbound_sms(
            payload={
                "id": "ATXid_stop",
                "from": "+254700000009",
                "to": "+254700000999",
                "text": "STOP",
                "date": "2026-04-23T12:30:00Z",
            },
            headers={},
            lead_id="lead_sms_cmd",
        )
    )

    assert event.event_type == "command_stop"
    assert repo.is_sms_allowed(lead_id="lead_sms_cmd") is False
