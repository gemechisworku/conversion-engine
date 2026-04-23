from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx

from agent.config.settings import Settings
from agent.services.calendar.calcom_client import CalComService, book_and_sync_crm
from agent.services.calendar.schemas import BookingRequest
from agent.services.crm.hubspot_mcp import HubSpotMCPService, map_enrichment_to_crm_payload
from agent.services.crm.schemas import CRMLeadPayload
from agent.services.policy.outbound_policy import OutboundPolicyService


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "hubspot_mcp_base_url": "https://hubspot-mcp.example.com",
        "hubspot_mcp_api_key": "hs_key",
        "calcom_api_url": "https://api.cal.com/v2",
        "calcom_api_key": "cal_key",
        "calcom_event_type_id": "evt_123",
        "challenge_mode": False,
        "sink_routing_enabled": True,
        "kill_switch_enabled": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_hubspot_write_includes_enrichment_fields() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"crm_event_id": "evt_001"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )

    enrichment = map_enrichment_to_crm_payload(
        lead_id="lead_1",
        enrichment_artifact={
            "signals": {
                "crunchbase": {"summary": "Series A recent"},
                "job_posts": {"summary": "Hiring increased"},
                "layoffs": {"summary": "No major layoffs"},
                "leadership_changes": {"summary": "CTO joined"},
            },
            "brief_references": ["brief_1"],
            "bench_match_status": "partial_match",
        },
    )
    result = asyncio.run(
        service.append_enrichment(
            lead_id="lead_1",
            enrichment=enrichment,
            trace_id="trace_1",
            idempotency_key="lead_1:enrich",
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is True
    assert captured["path"] == "/crm/event"
    payload = captured["json"]["payload"]
    assert payload["funding_signal_summary"] == "Series A recent"
    assert payload["job_velocity_summary"] == "Hiring increased"
    assert payload["layoffs_signal_summary"] == "No major layoffs"
    assert payload["leadership_signal_summary"] == "CTO joined"


def test_calcom_booking_returns_normalized_object() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/schedule/book"
        return httpx.Response(200, json={"data": {"booking_id": "bk_100", "status": "confirmed"}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    cal_service = CalComService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )

    req = BookingRequest(
        lead_id="lead_1",
        trace_id="trace_1",
        slot_id="slot_1",
        starts_at=datetime.fromisoformat("2026-04-24T10:00:00+00:00"),
        ends_at=datetime.fromisoformat("2026-04-24T10:30:00+00:00"),
        timezone="UTC",
        prospect_email="prospect@example.com",
        confirmed_by_prospect=True,
        idempotency_key="lead_1:slot_1",
    )
    result = asyncio.run(cal_service.book_discovery_call(req))
    asyncio.run(http_client.aclose())

    assert result.succeeded is True
    assert result.booking_id == "bk_100"
    assert result.status == "confirmed"


def test_successful_booking_triggers_hubspot_update() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/schedule/book"):
            return httpx.Response(200, json={"data": {"booking_id": "bk_200", "status": "confirmed"}})
        return httpx.Response(200, json={"crm_event_id": "evt_200"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    policy = OutboundPolicyService(settings)
    cal_service = CalComService(settings=settings, policy_service=policy, http_client=http_client)
    hub_service = HubSpotMCPService(settings=settings, policy_service=policy, http_client=http_client)

    req = BookingRequest(
        lead_id="lead_2",
        trace_id="trace_2",
        slot_id="slot_2",
        starts_at=datetime.fromisoformat("2026-04-24T11:00:00+00:00"),
        ends_at=datetime.fromisoformat("2026-04-24T11:30:00+00:00"),
        timezone="UTC",
        prospect_email="prospect2@example.com",
        confirmed_by_prospect=True,
        idempotency_key="lead_2:slot_2",
    )

    linked = asyncio.run(
        book_and_sync_crm(
            lead_id="lead_2",
            booking_request=req,
            calcom_service=cal_service,
            hubspot_service=hub_service,
        )
    )
    asyncio.run(http_client.aclose())

    assert linked.booking.succeeded is True
    assert linked.crm_write is not None
    assert linked.crm_write.succeeded is True
    assert "/v2/schedule/book" in calls
    assert "/crm/event" in calls


def test_booking_failure_does_not_update_crm() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/schedule/book"):
            return httpx.Response(200, json={"data": {"status": "failed"}})
        return httpx.Response(200, json={"crm_event_id": "evt_999"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    policy = OutboundPolicyService(settings)
    cal_service = CalComService(settings=settings, policy_service=policy, http_client=http_client)
    hub_service = HubSpotMCPService(settings=settings, policy_service=policy, http_client=http_client)

    req = BookingRequest(
        lead_id="lead_3",
        trace_id="trace_3",
        slot_id="slot_3",
        starts_at=datetime.fromisoformat("2026-04-24T12:00:00+00:00"),
        ends_at=datetime.fromisoformat("2026-04-24T12:30:00+00:00"),
        timezone="UTC",
        prospect_email="prospect3@example.com",
        confirmed_by_prospect=True,
        idempotency_key="lead_3:slot_3",
    )

    linked = asyncio.run(
        book_and_sync_crm(
            lead_id="lead_3",
            booking_request=req,
            calcom_service=cal_service,
            hubspot_service=hub_service,
        )
    )
    asyncio.run(http_client.aclose())

    assert linked.booking.succeeded is False
    assert linked.crm_write is None
    assert calls.count("/crm/event") == 0


def test_hubspot_retries_on_server_failure_then_succeeds() -> None:
    call_count = {"value": 0}

    async def handler(_: httpx.Request) -> httpx.Response:
        call_count["value"] += 1
        if call_count["value"] == 1:
            return httpx.Response(500, json={"message": "temporary"})
        return httpx.Response(200, json={"crm_record_id": "rec_1"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    result = asyncio.run(
        service.upsert_contact(
            contact=CRMLeadPayload(
                lead_id="lead_retry",
                company_id="comp_1",
                company_name="Retry Inc",
            ),
            trace_id="trace_retry",
            idempotency_key="lead_retry",
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is True
    assert call_count["value"] == 2
