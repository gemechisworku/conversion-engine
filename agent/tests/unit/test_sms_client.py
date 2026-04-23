from __future__ import annotations

import asyncio
import httpx

from agent.config.settings import Settings
from agent.services.policy.channel_policy import LeadChannelState
from agent.services.policy.outbound_policy import OutboundPolicyService
from agent.services.sms.client import SMSService
from agent.services.sms.router import SMSRouter
from agent.services.sms.schemas import OutboundSMSRequest
from agent.services.sms.webhook import AfricasTalkingWebhookParser


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "africastalking_username": "sandbox",
        "africastalking_api_key": "at_key",
        "africastalking_api_url": "https://api.africastalking.com/version1/messaging",
        "africastalking_webhook_secret": "",
        "challenge_mode": False,
        "sink_routing_enabled": True,
        "kill_switch_enabled": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _request(*, warm: bool) -> OutboundSMSRequest:
    return OutboundSMSRequest(
        lead_id="lead_1",
        draft_id="draft_sms_1",
        review_id="review_sms_1",
        trace_id="trace_sms_1",
        idempotency_key="idem_sms_1",
        to_number="+254700000001",
        message="Hello from Tenacious",
        lead_channel_state=LeadChannelState(
            lead_id="lead_1",
            has_prior_email_reply=warm,
            explicit_warm_status=warm,
        ),
    )


def _service(settings: Settings, http_client: httpx.AsyncClient | None = None) -> SMSService:
    return SMSService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        parser=AfricasTalkingWebhookParser(settings),
        router=SMSRouter(),
        http_client=http_client,
    )


def test_outbound_sms_allowed_for_warm_lead() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apiKey"] == "at_key"
        body = (await request.aread()).decode("utf-8")
        assert "message=Hello+from+Tenacious" in body
        return httpx.Response(
            201,
            json={
                "SMSMessageData": {
                    "Recipients": [{"status": "Success", "messageId": "ATXid_001", "number": "+254700000001"}]
                }
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = _service(_settings(), http_client=http_client)

    result = asyncio.run(service.send_warm_lead_sms(_request(warm=True)))
    asyncio.run(http_client.aclose())

    assert result.accepted is True
    assert result.provider_message_id == "ATXid_001"


def test_outbound_sms_blocked_for_cold_lead() -> None:
    settings = _settings()
    service = _service(settings)

    result = asyncio.run(service.send_warm_lead_sms(_request(warm=False)))

    assert result.accepted is False
    assert result.raw_status == "blocked"
    assert result.error is not None
    assert result.error.error_code == "POLICY_BLOCKED"


def test_outbound_sms_provider_failure_visible() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"SMSMessageData": {"Message": "Invalid number"}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = _service(_settings(), http_client=http_client)

    result = asyncio.run(service.send_warm_lead_sms(_request(warm=True)))
    asyncio.run(http_client.aclose())

    assert result.accepted is False
    assert result.error is not None
    assert result.error.error_code == "DELIVERY_FAILED"


def test_outbound_sms_retries_then_succeeds() -> None:
    state = {"calls": 0}

    async def handler(_: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(500, json={"SMSMessageData": {"Message": "Temporary"}})
        return httpx.Response(
            201,
            json={
                "SMSMessageData": {
                    "Recipients": [{"status": "Success", "messageId": "ATXid_retry", "number": "+254700000001"}]
                }
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    service = SMSService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        parser=AfricasTalkingWebhookParser(settings),
        router=SMSRouter(),
        http_client=http_client,
        max_retries=2,
    )

    result = asyncio.run(service.send_warm_lead_sms(_request(warm=True)))
    asyncio.run(http_client.aclose())

    assert result.accepted is True
    assert result.provider_message_id == "ATXid_retry"
    assert state["calls"] == 2
