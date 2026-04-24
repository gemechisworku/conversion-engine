from __future__ import annotations

import asyncio
import json

import httpx

from agent.config.settings import Settings
from agent.services.email.client import ResendEmailClient
from agent.services.email.schemas import OutboundEmailRequest
from agent.services.policy.outbound_policy import OutboundPolicyService


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "resend_api_key": "test_key",
        "resend_api_url": "https://api.resend.com",
        "resend_from_email": "outreach@tenacious.example",
        "resend_webhook_secret": "",
        "challenge_mode": False,
        "sink_routing_enabled": False,
        "kill_switch_enabled": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _request(*, review_status: str = "approved") -> OutboundEmailRequest:
    return OutboundEmailRequest(
        lead_id="lead_123",
        draft_id="draft_123",
        review_id="review_123",
        review_status=review_status,
        trace_id="trace_123",
        idempotency_key="idem_123",
        to_email="prospect@example.com",
        subject="Quick intro",
        text_body="Hello from Tenacious",
    )


def test_send_email_success_returns_normalized_result() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/emails"
        assert request.headers["Idempotency-Key"] == "idem_123"
        payload = await request.aread()
        assert b"Quick intro" in payload
        assert b"X-Tenacious-Status" in payload
        return httpx.Response(202, json={"id": "re_msg_123"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ResendEmailClient(
        settings=_settings(),
        policy_service=OutboundPolicyService(_settings()),
        http_client=http_client,
    )

    result = asyncio.run(client.send_email(_request()))
    asyncio.run(http_client.aclose())

    assert result.accepted is True
    assert result.provider == "resend"
    assert result.provider_message_id == "re_msg_123"
    assert result.error is None


def test_send_email_failure_returns_delivery_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ResendEmailClient(
        settings=_settings(),
        policy_service=OutboundPolicyService(_settings()),
        http_client=http_client,
    )

    result = asyncio.run(client.send_email(_request()))
    asyncio.run(http_client.aclose())

    assert result.accepted is False
    assert result.error is not None
    assert result.error.error_code == "DELIVERY_FAILED"


def test_send_email_blocked_when_policy_blocks_outbound() -> None:
    settings = _settings(challenge_mode=True, sink_routing_enabled=False)
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(202, json={"id": "unused"}))
    )
    client = ResendEmailClient(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )

    result = asyncio.run(client.send_email(_request()))
    asyncio.run(http_client.aclose())

    assert result.accepted is False
    assert result.raw_status == "blocked"
    assert result.error is not None
    assert result.error.error_code == "POLICY_BLOCKED"


def test_send_email_retries_transient_failure_then_succeeds() -> None:
    state = {"calls": 0}

    async def handler(_: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(500, json={"message": "temporary"})
        return httpx.Response(202, json={"id": "re_msg_retry"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ResendEmailClient(
        settings=_settings(),
        policy_service=OutboundPolicyService(_settings()),
        http_client=http_client,
        max_retries=2,
    )

    result = asyncio.run(client.send_email(_request()))
    asyncio.run(http_client.aclose())

    assert result.accepted is True
    assert result.provider_message_id == "re_msg_retry"
    assert state["calls"] == 2


def test_send_email_includes_threading_headers_when_set() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads((await request.aread()).decode())
        return httpx.Response(202, json={"id": "re_thread"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ResendEmailClient(
        settings=_settings(),
        policy_service=OutboundPolicyService(_settings()),
        http_client=http_client,
    )
    req = OutboundEmailRequest(
        lead_id="lead_123",
        draft_id="draft_123",
        review_id="review_123",
        trace_id="trace_123",
        idempotency_key="idem_thread",
        to_email="prospect@example.com",
        subject="Re: Intro",
        text_body="Follow-up",
        in_reply_to="<inbound-msg@example.com>",
        references="<a@b> <inbound-msg@example.com>",
        metadata={"email_thread_id": "emthr_test1", "tenacious_status": "approved", "bench_verified": True},
    )
    result = asyncio.run(client.send_email(req))
    asyncio.run(http_client.aclose())

    assert result.accepted is True
    hdr = captured["json"]["headers"]
    assert hdr["In-Reply-To"] == "<inbound-msg@example.com>"
    assert "<a@b>" in hdr["References"]
    assert hdr["X-Email-Thread-Id"] == "emthr_test1"


def test_send_email_blocked_without_approved_review() -> None:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(202, json={"id": "unused"})))
    client = ResendEmailClient(
        settings=_settings(),
        policy_service=OutboundPolicyService(_settings()),
        http_client=http_client,
    )
    result = asyncio.run(client.send_email(_request(review_status="pending")))
    asyncio.run(http_client.aclose())

    assert result.accepted is False
    assert result.error is not None
    assert result.error.error_code == "POLICY_BLOCKED"
