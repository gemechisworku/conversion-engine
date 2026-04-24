from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx
import pytest

from agent.config.settings import Settings
from agent.services.calendar.calcom_client import CalComService, book_and_sync_crm
from agent.services.calendar.schemas import AvailabilityRequest, BookingRequest
from agent.services.crm.hubspot_mcp import HubSpotMCPService, map_enrichment_to_crm_payload
from agent.services.crm.schemas import CRMBookingPayload, CRMLeadPayload
from agent.services.policy.outbound_policy import OutboundPolicyService


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "hubspot_mcp_server_url": "https://mcp.hubspot.com",
        "hubspot_mcp_access_token": "hs_access",
        "hubspot_mcp_refresh_token": "",
        "hubspot_mcp_client_id": "",
        "hubspot_mcp_client_secret": "",
        "hubspot_mcp_tool_upsert_lead": "upsert_lead",
        "hubspot_mcp_tool_append_event": "append_event",
        "calcom_api_url": "https://api.cal.com/v2",
        "calcom_api_key": "cal_key",
        "calcom_event_type_id": "",
        "calcom_event_type_slug": "test-booking",
        "calcom_username": "demo-user",
        "challenge_mode": False,
        "sink_routing_enabled": True,
        "kill_switch_enabled": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_hubspot_write_includes_enrichment_fields() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_1"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            captured["tool"] = payload["params"]["name"]
            captured["args"] = payload["params"]["arguments"]
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"structuredContent": {"crm_event_id": "evt_001"}},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

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
    assert captured["tool"] == "append_event"
    payload = captured["args"]["payload"]
    assert payload["funding_signal_summary"] == "Series A recent"
    assert payload["job_velocity_summary"] == "Hiring increased"
    assert payload["layoffs_signal_summary"] == "No major layoffs"
    assert payload["leadership_signal_summary"] == "CTO joined"


def test_calcom_booking_returns_normalized_object() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/bookings"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["eventTypeSlug"] == "test-booking"
        assert payload["username"] == "demo-user"
        assert "eventTypeId" not in payload
        assert payload["attendee"]["name"] == "Prospect"
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
    tools_called: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bookings"):
            calls.append(request.url.path)
            return httpx.Response(200, json={"data": {"booking_id": "bk_200", "status": "confirmed"}})
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_2"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            tools_called.append(payload["params"]["name"])
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"structuredContent": {"crm_event_id": "evt_200"}},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

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
    assert "/v2/bookings" in calls
    assert "append_event" in tools_called


def test_booking_failure_does_not_update_crm() -> None:
    calls: list[str] = []
    tools_called: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bookings"):
            calls.append(request.url.path)
            return httpx.Response(200, json={"data": {"status": "failed"}})
        payload = json.loads(request.content.decode("utf-8"))
        if payload.get("method") == "tools/call":
            tools_called.append(payload["params"]["name"])
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {"structuredContent": {"crm_event_id": "evt_999"}},
            },
        )

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
    assert tools_called == []


def test_calcom_slot_lookup_parses_range_slots() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v2/slots"
        assert request.url.params.get("eventTypeSlug") == "test-booking"
        assert request.url.params.get("username") == "demo-user"
        assert request.url.params.get("eventTypeId") is None
        assert request.url.params.get("timeZone") == "UTC"
        assert request.url.params.get("format") == "range"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "2026-04-24": [
                        {"start": "2026-04-24T10:00:00Z", "end": "2026-04-24T10:30:00Z"},
                    ]
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    service = CalComService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )

    slots = asyncio.run(
        service.get_available_slots(
            AvailabilityRequest(
                lead_id="lead_slots",
                trace_id="trace_slots",
                timezone="UTC",
                window_start=datetime.fromisoformat("2026-04-24T09:00:00+00:00"),
                window_end=datetime.fromisoformat("2026-04-24T12:00:00+00:00"),
            )
        )
    )
    asyncio.run(http_client.aclose())

    assert len(slots) == 1
    assert slots[0].start_at == datetime.fromisoformat("2026-04-24T10:00:00+00:00")
    assert slots[0].end_at == datetime.fromisoformat("2026-04-24T10:30:00+00:00")


def test_calcom_slot_lookup_raises_on_http_failure() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": "error"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    service = CalComService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )

    with pytest.raises(RuntimeError, match="HTTP 401"):
        asyncio.run(
            service.get_available_slots(
                AvailabilityRequest(
                    lead_id="lead_slots_fail",
                    trace_id="trace_slots_fail",
                    timezone="UTC",
                    window_start=datetime.fromisoformat("2026-04-24T09:00:00+00:00"),
                    window_end=datetime.fromisoformat("2026-04-24T12:00:00+00:00"),
                )
            )
        )
    asyncio.run(http_client.aclose())


def test_calcom_selector_supports_event_type_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v2/slots"
        assert request.url.params.get("eventTypeId") == "987"
        assert request.url.params.get("eventTypeSlug") is None
        assert request.url.params.get("username") is None
        return httpx.Response(200, json={"status": "success", "data": {}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(
        calcom_event_type_id="987",
        calcom_event_type_slug="",
        calcom_username="",
    )
    service = CalComService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    slots = asyncio.run(
        service.get_available_slots(
            AvailabilityRequest(
                lead_id="lead_slots_id",
                trace_id="trace_slots_id",
                timezone="UTC",
                window_start=datetime.fromisoformat("2026-04-24T09:00:00+00:00"),
                window_end=datetime.fromisoformat("2026-04-24T12:00:00+00:00"),
            )
        )
    )
    asyncio.run(http_client.aclose())

    assert slots == []


def test_calcom_booking_uses_provided_prospect_name() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["attendee"]["name"] == "Game Worku"
        return httpx.Response(200, json={"data": {"booking_id": "bk_777", "status": "confirmed"}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    service = CalComService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    result = asyncio.run(
        service.book_discovery_call(
            BookingRequest(
                lead_id="lead_with_name",
                trace_id="trace_with_name",
                slot_id="slot_with_name",
                starts_at=datetime.fromisoformat("2026-04-24T13:00:00+00:00"),
                ends_at=datetime.fromisoformat("2026-04-24T13:30:00+00:00"),
                timezone="UTC",
                prospect_email="prospect@example.com",
                prospect_name="  Game Worku  ",
                confirmed_by_prospect=True,
                idempotency_key="lead_with_name:slot",
            )
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is True


def test_hubspot_retries_on_server_failure_then_succeeds() -> None:
    call_count = {"value": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_retry"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            call_count["value"] += 1
            if call_count["value"] == 1:
                return httpx.Response(500, json={"message": "temporary"})
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"structuredContent": {"crm_record_id": "rec_1"}},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

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


def test_hubspot_requires_access_token_or_refresh_credentials() -> None:
    settings = _settings(
        hubspot_mcp_access_token="",
        hubspot_mcp_refresh_token="",
        hubspot_mcp_client_id="",
        hubspot_mcp_client_secret="",
    )
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
    )
    result = asyncio.run(
        service.record_booking(
            lead_id="lead_cfg",
            booking=CRMBookingPayload(
                lead_id="lead_cfg",
                booking_id="booking_cfg",
                slot_id="slot_cfg",
                status="confirmed",
                timezone="UTC",
            ),
            trace_id="trace_cfg",
            idempotency_key="lead_cfg:slot_cfg",
        )
    )

    assert result.succeeded is False
    assert result.error is not None
    assert result.error.error_code == "CONFIG_ERROR"


def test_hubspot_refreshes_token_after_401() -> None:
    seen_auth_headers: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/v1/token"):
            return httpx.Response(200, json={"access_token": "fresh_token", "refresh_token": "fresh_refresh"})

        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            seen_auth_headers.append(request.headers.get("Authorization", ""))
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_refresh"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            seen_auth_headers.append(request.headers.get("Authorization", ""))
            return httpx.Response(202)
        if method == "tools/call":
            seen_auth_headers.append(request.headers.get("Authorization", ""))
            if request.headers.get("Authorization") == "Bearer expired_token":
                return httpx.Response(401, json={"error": "expired"})
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"structuredContent": {"crm_event_id": "evt_after_refresh"}},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(
        hubspot_mcp_access_token="expired_token",
        hubspot_mcp_refresh_token="refresh_token",
        hubspot_mcp_client_id="client_id",
        hubspot_mcp_client_secret="client_secret",
        hubspot_mcp_tool_append_event="append_event",
    )
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    result = asyncio.run(
        service.record_booking(
            lead_id="lead_cfg_refresh",
            booking=CRMBookingPayload(
                lead_id="lead_cfg_refresh",
                booking_id="booking_cfg_refresh",
                slot_id="slot_cfg_refresh",
                status="confirmed",
                timezone="UTC",
            ),
            trace_id="trace_cfg_refresh",
            idempotency_key="lead_cfg_refresh:slot_cfg_refresh",
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is True
    assert "Bearer expired_token" in seen_auth_headers
    assert "Bearer fresh_token" in seen_auth_headers


def test_manage_crm_objects_mapping_for_booking_event() -> None:
    captured_calls: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_manage_evt"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            call = {
                "name": payload["params"]["name"],
                "args": payload["params"]["arguments"],
            }
            captured_calls.append(call)
            if call["name"] == "search_crm_objects":
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {"content": [{"type": "text", "text": "{\"results\": [{\"id\": 12345}]}"}]},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"structuredContent": {"crm_event_id": "evt_manage"}},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(hubspot_mcp_tool_append_event="manage_crm_objects")
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    result = asyncio.run(
        service.record_booking(
            lead_id="lead_manage_evt",
            booking=CRMBookingPayload(
                lead_id="lead_manage_evt",
                booking_id="booking_manage_evt",
                slot_id="slot_manage_evt",
                status="confirmed",
                timezone="UTC",
            ),
            trace_id="trace_manage_evt",
            idempotency_key="lead_manage_evt:slot_manage_evt",
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is True
    assert result.raw_response["projection"]["applied"] is True
    manage_calls = [call for call in captured_calls if call["name"] == "manage_crm_objects"]
    assert len(manage_calls) == 2

    projection_args = manage_calls[0]["args"]
    assert isinstance(projection_args, dict)
    assert projection_args["confirmationStatus"] == "CONFIRMATION_WAIVED_FOR_SESSION"
    projection_objects = projection_args["updateRequest"]["objects"]
    assert projection_objects[0]["objectType"] == "companies"
    assert projection_objects[0]["objectId"] == 12345
    assert "description" in projection_objects[0]["properties"]
    assert "booking_manage_evt" in projection_objects[0]["properties"]["description"]

    note_args = manage_calls[1]["args"]
    assert isinstance(note_args, dict)
    assert note_args["confirmationStatus"] == "CONFIRMATION_WAIVED_FOR_SESSION"
    objects = note_args["createRequest"]["objects"]
    assert objects[0]["objectType"] == "notes"
    note_body = objects[0]["properties"]["hs_note_body"]
    assert "Booking confirmed" in note_body
    assert "booking_manage_evt" in note_body
    associations = objects[0]["associations"]
    assert associations[0]["targetObjectId"] == 12345
    assert associations[0]["targetObjectType"] == "companies"


def test_manage_crm_objects_projection_writes_configured_booking_properties() -> None:
    captured_calls: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_manage_evt_props"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            call = {
                "name": payload["params"]["name"],
                "args": payload["params"]["arguments"],
            }
            captured_calls.append(call)
            if call["name"] == "search_crm_objects":
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {"content": [{"type": "text", "text": "{\"results\": [{\"id\": 12345}]}"}]},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"structuredContent": {"crm_event_id": "evt_manage_props"}},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(
        hubspot_mcp_tool_append_event="manage_crm_objects",
        hubspot_company_prop_last_booking_id="ce_last_booking_id",
        hubspot_company_prop_last_booking_start_at="ce_last_booking_start_at",
        hubspot_company_prop_last_booking_end_at="ce_last_booking_end_at",
        hubspot_company_prop_last_booking_timezone="ce_last_booking_timezone",
        hubspot_company_prop_last_booking_url="ce_last_booking_url",
        hubspot_company_prop_last_booking_status="ce_last_booking_status",
    )
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    result = asyncio.run(
        service.record_booking(
            lead_id="lead_manage_evt_props",
            booking=CRMBookingPayload(
                lead_id="lead_manage_evt_props",
                booking_id="booking_manage_evt_props",
                slot_id="slot_manage_evt_props",
                status="confirmed",
                timezone="UTC",
                calendar_ref="https://app.cal.com/video/test-booking",
                starts_at=datetime.fromisoformat("2026-04-27T06:15:00+00:00"),
                ends_at=datetime.fromisoformat("2026-04-27T06:30:00+00:00"),
            ),
            trace_id="trace_manage_evt_props",
            idempotency_key="lead_manage_evt_props:slot_manage_evt_props",
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is True
    assert result.raw_response["projection"]["applied"] is True
    manage_calls = [call for call in captured_calls if call["name"] == "manage_crm_objects"]
    assert len(manage_calls) == 2
    projection_args = manage_calls[0]["args"]
    assert isinstance(projection_args, dict)
    projection_objects = projection_args["updateRequest"]["objects"]
    props = projection_objects[0]["properties"]
    assert props["ce_last_booking_id"] == "booking_manage_evt_props"
    assert props["ce_last_booking_start_at"] == "2026-04-27T06:15:00Z"
    assert props["ce_last_booking_end_at"] == "2026-04-27T06:30:00Z"
    assert props["ce_last_booking_timezone"] == "UTC"
    assert props["ce_last_booking_url"] == "https://app.cal.com/video/test-booking"
    assert props["ce_last_booking_status"] == "confirmed"


def test_manage_crm_objects_projection_failure_is_reported_in_raw_response() -> None:
    manage_call_count = {"value": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_manage_evt_projection_fail"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            if payload["params"]["name"] == "search_crm_objects":
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {"content": [{"type": "text", "text": "{\"results\": [{\"id\": 12345}]}"}]},
                    },
                )
            if payload["params"]["name"] == "manage_crm_objects":
                manage_call_count["value"] += 1
                if manage_call_count["value"] == 1:
                    return httpx.Response(
                        200,
                        json={
                            "jsonrpc": "2.0",
                            "id": payload["id"],
                            "result": {
                                "isError": True,
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "{\"errorMessage\":\"Property values were not valid\"}",
                                    }
                                ],
                            },
                        },
                    )
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {"structuredContent": {"crm_event_id": "evt_manage_after_projection_fail"}},
                    },
                )
        raise AssertionError(f"unexpected MCP method: {method}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(hubspot_mcp_tool_append_event="manage_crm_objects")
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    result = asyncio.run(
        service.record_booking(
            lead_id="lead_manage_evt_projection_fail",
            booking=CRMBookingPayload(
                lead_id="lead_manage_evt_projection_fail",
                booking_id="booking_manage_evt_projection_fail",
                slot_id="slot_manage_evt_projection_fail",
                status="confirmed",
                timezone="UTC",
            ),
            trace_id="trace_manage_evt_projection_fail",
            idempotency_key="lead_manage_evt_projection_fail:slot_manage_evt_projection_fail",
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is True
    assert result.raw_response["projection"]["applied"] is False
    assert "Property values were not valid" in result.raw_response["projection"]["error"]


def test_manage_crm_objects_mapping_for_lead_upsert() -> None:
    captured_calls: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_manage_upsert"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            call = {
                "name": payload["params"]["name"],
                "args": payload["params"]["arguments"],
            }
            captured_calls.append(call)
            if call["name"] == "search_crm_objects":
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {"content": [{"type": "text", "text": "{\"results\": []}"}]},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"structuredContent": {"crm_record_id": "rec_manage"}},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(hubspot_mcp_tool_upsert_lead="manage_crm_objects")
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    result = asyncio.run(
        service.upsert_contact(
            contact=CRMLeadPayload(
                lead_id="lead_manage_upsert",
                company_id="company_manage_upsert",
                company_name="Manage Corp",
                company_domain="manage.example.com",
            ),
            trace_id="trace_manage_upsert",
            idempotency_key="lead_manage_upsert",
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is True
    tool_names = [str(call["name"]) for call in captured_calls]
    assert "search_crm_objects" in tool_names
    assert "manage_crm_objects" in tool_names
    manage_call = next(call for call in captured_calls if call["name"] == "manage_crm_objects")
    args = manage_call["args"]
    assert isinstance(args, dict)
    assert args["confirmationStatus"] == "CONFIRMATION_WAIVED_FOR_SESSION"
    objects = args["createRequest"]["objects"]
    assert objects[0]["objectType"] == "companies"
    assert objects[0]["properties"]["name"] == "Manage Corp"


def test_hubspot_marks_tool_iserror_as_failed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_err"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            if payload["params"]["name"] == "search_crm_objects":
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "result": {"content": [{"type": "text", "text": "{\"results\": [{\"id\": 12345}]}"}]},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "{\"errorMessage\":\"A non-empty list of objects to create or update must be provided\"}",
                            }
                        ],
                    },
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(
        hubspot_mcp_tool_append_event="manage_crm_objects",
    )
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    result = asyncio.run(
        service.record_booking(
            lead_id="lead_tool_err",
            booking=CRMBookingPayload(
                lead_id="lead_tool_err",
                booking_id="booking_tool_err",
                slot_id="slot_tool_err",
                status="confirmed",
                timezone="UTC",
            ),
            trace_id="trace_tool_err",
            idempotency_key="lead_tool_err:slot_tool_err",
        )
    )
    asyncio.run(http_client.aclose())

    assert result.succeeded is False
    assert result.error is not None
    assert result.error.error_code == "CRM_SYNC_FAILED"
    assert "A non-empty list of objects" in result.error.error_message


def test_hubspot_tool_readiness_requires_minimum_count() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess_tools"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            tools = [{"name": f"tool_{idx}"} for idx in range(9)]
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"tools": tools},
                },
            )
        raise AssertionError(f"unexpected MCP method: {method}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(hubspot_mcp_required_tool_count=9)
    service = HubSpotMCPService(
        settings=settings,
        policy_service=OutboundPolicyService(settings),
        http_client=http_client,
    )
    readiness = asyncio.run(service.verify_tool_readiness())
    asyncio.run(http_client.aclose())

    assert readiness["ready"] is True
    assert readiness["discovered_count"] >= 9
