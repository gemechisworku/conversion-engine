"""Live smoke commands for provider integrations."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

# Allow running directly via `python agent/scripts/live_smoke.py ...`
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.config.logging import configure_logging
from agent.config.settings import get_settings
from agent.main import build_calcom_service, build_email_service, build_hubspot_service, build_sms_service
from agent.services.calendar.calcom_client import book_and_sync_crm
from agent.services.calendar.schemas import AvailabilityRequest, BookingRequest
from agent.services.crm.schemas import CRMBookingPayload
from agent.services.email.schemas import OutboundEmailRequest
from agent.services.policy.channel_policy import LeadChannelState
from agent.services.sms.schemas import OutboundSMSRequest


def _new_trace(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _ensure_live_policy_allows_side_effects() -> None:
    settings = get_settings()
    # Implements: FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: policy_decision.md
    # API: policy_api.md
    if settings.challenge_mode and not settings.sink_routing_enabled:
        raise SystemExit(
            "Live side-effect commands are blocked by policy: CHALLENGE_MODE=true and "
            "SINK_ROUTING_ENABLED=false. Set SINK_ROUTING_ENABLED=true (or CHALLENGE_MODE=false) in .env."
        )


def _ensure_hubspot_is_configured() -> None:
    settings = get_settings()
    # Implements: FR-12
    # Workflow: crm_sync.md
    # Schema: crm_event.md
    # API: crm_api.md
    has_access_token = bool(settings.hubspot_mcp_access_token.strip())
    has_refresh_flow = bool(
        settings.hubspot_mcp_refresh_token.strip()
        and settings.hubspot_mcp_client_id.strip()
        and settings.hubspot_mcp_client_secret.strip()
    )
    if not has_access_token and not has_refresh_flow:
        raise SystemExit(
            "HubSpot sync is not configured. Set HUBSPOT_MCP_ACCESS_TOKEN, or set "
            "HUBSPOT_MCP_REFRESH_TOKEN + HUBSPOT_MCP_CLIENT_ID + HUBSPOT_MCP_CLIENT_SECRET in .env."
        )


async def run_email(args: argparse.Namespace) -> None:
    _ensure_live_policy_allows_side_effects()
    service = build_email_service()
    lead_id = args.lead_id or _new_id("lead")
    request = OutboundEmailRequest(
        lead_id=lead_id,
        draft_id=_new_id("draft"),
        review_id=_new_id("review"),
        trace_id=_new_trace("trace_email"),
        idempotency_key=_new_id("idem_email"),
        to_email=args.to,
        subject=args.subject,
        text_body=args.body,
    )
    result = await service.send_email(request)
    print(json.dumps(result.model_dump(mode="json"), indent=2))


async def run_sms(args: argparse.Namespace) -> None:
    _ensure_live_policy_allows_side_effects()
    service = build_sms_service()
    lead_id = args.lead_id or _new_id("lead")
    request = OutboundSMSRequest(
        lead_id=lead_id,
        draft_id=_new_id("draft"),
        review_id=_new_id("review"),
        trace_id=_new_trace("trace_sms"),
        idempotency_key=_new_id("idem_sms"),
        to_number=args.to,
        message=args.message,
        lead_channel_state=LeadChannelState(
            lead_id=lead_id,
            has_prior_email_reply=not args.cold,
            explicit_warm_status=not args.cold,
            has_recent_inbound_sms=False,
        ),
    )
    result = await service.send_warm_lead_sms(request)
    print(json.dumps(result.model_dump(mode="json"), indent=2))


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


async def run_booking_sync(args: argparse.Namespace) -> None:
    _ensure_live_policy_allows_side_effects()
    calcom = build_calcom_service()

    lead_id = args.lead_id or _new_id("lead")
    trace_id = _new_trace("trace_booking")

    if args.start and args.end:
        start_at = _parse_dt(args.start)
        end_at = _parse_dt(args.end)
        slot_id = args.slot_id or _new_id("slot")
    else:
        window_start = datetime.now(UTC) + timedelta(hours=1)
        window_end = window_start + timedelta(days=7)
        try:
            slots = await calcom.get_available_slots(
                AvailabilityRequest(
                    lead_id=lead_id,
                    trace_id=trace_id,
                    timezone=args.timezone,
                    window_start=window_start,
                    window_end=window_end,
                )
            )
        except Exception as exc:
            raise SystemExit(f"Cal.com slot lookup failed: {exc}") from exc
        if not slots:
            raise SystemExit("No available slots returned by Cal.com for the selected window.")
        chosen = slots[0]
        start_at = chosen.start_at
        end_at = chosen.end_at
        slot_id = chosen.slot_id

    request = BookingRequest(
        lead_id=lead_id,
        trace_id=trace_id,
        slot_id=slot_id,
        starts_at=start_at,
        ends_at=end_at,
        timezone=args.timezone,
        prospect_email=args.prospect_email,
        prospect_name=args.prospect_name,
        confirmed_by_prospect=not args.unconfirmed,
        idempotency_key=_new_id("idem_booking"),
    )
    if args.skip_crm:
        booking = await calcom.book_discovery_call(request)
        print(
            json.dumps(
                {
                    "booking": booking.model_dump(mode="json"),
                    "crm_write": None,
                    "crm_skipped": True,
                },
                indent=2,
            )
        )
        return

    _ensure_hubspot_is_configured()
    hubspot = build_hubspot_service()
    linked = await book_and_sync_crm(
        lead_id=lead_id,
        booking_request=request,
        calcom_service=calcom,
        hubspot_service=hubspot,
        company_name=args.company_name or None,
        company_domain=args.company_domain or None,
    )
    print(json.dumps(linked.model_dump(mode="json"), indent=2))


async def run_hubspot_booking(args: argparse.Namespace) -> None:
    _ensure_live_policy_allows_side_effects()
    _ensure_hubspot_is_configured()
    hubspot = build_hubspot_service()

    lead_id = args.lead_id or _new_id("lead")
    trace_id = _new_trace("trace_hubspot")
    starts_at = _parse_dt(args.start) if args.start else datetime.now(UTC) + timedelta(hours=1)
    ends_at = _parse_dt(args.end) if args.end else starts_at + timedelta(minutes=30)
    slot_id = args.slot_id or _new_id("slot")
    booking_id = args.booking_id or _new_id("booking")

    payload = CRMBookingPayload(
        lead_id=lead_id,
        booking_id=booking_id,
        slot_id=slot_id,
        status=args.status,
        timezone=args.timezone,
        calendar_ref=args.calendar_ref or None,
        starts_at=starts_at,
        ends_at=ends_at,
        confirmed_by_prospect=not args.unconfirmed,
    )
    result = await hubspot.record_booking(
        lead_id=lead_id,
        booking=payload,
        trace_id=trace_id,
        idempotency_key=args.idempotency_key or f"{lead_id}:{slot_id}",
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))


async def run_hubspot_tools(_: argparse.Namespace) -> None:
    _ensure_hubspot_is_configured()
    hubspot = build_hubspot_service()
    tools = await hubspot.list_tools()
    readiness = await hubspot.verify_tool_readiness()
    print(json.dumps({"count": len(tools), "tools": tools, "readiness": readiness}, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live smoke tests for conversion-engine integrations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    email = subparsers.add_parser("email", help="Send one live email via Resend.")
    email.add_argument("--to", required=True, help="Recipient email address.")
    email.add_argument("--subject", default="Tenacious live smoke test")
    email.add_argument("--body", default="This is a live smoke test email from conversion-engine.")
    email.add_argument("--lead-id", default="", help="Optional fixed lead_id for traceability.")

    sms = subparsers.add_parser("sms", help="Send one live SMS via Africa's Talking.")
    sms.add_argument("--to", required=True, help="Recipient phone number in international format.")
    sms.add_argument("--message", default="Tenacious live smoke test SMS.")
    sms.add_argument("--lead-id", default="", help="Optional fixed lead_id for traceability.")
    sms.add_argument(
        "--cold",
        action="store_true",
        help="Send with cold-lead context to verify policy block behavior.",
    )

    booking = subparsers.add_parser("booking-sync", help="Book in Cal.com and sync booking to HubSpot MCP.")
    booking.add_argument("--prospect-email", required=True, help="Prospect email used for the booking attendee.")
    booking.add_argument("--prospect-name", default=None)
    booking.add_argument("--timezone", default="UTC")
    booking.add_argument("--lead-id", default="", help="Optional fixed lead_id for traceability.")
    booking.add_argument("--company-name", default="", help="Optional company name for HubSpot event association.")
    booking.add_argument("--company-domain", default="", help="Optional company domain for HubSpot event association.")
    booking.add_argument("--slot-id", default="", help="Optional explicit slot id.")
    booking.add_argument("--start", default="", help="Optional booking start datetime ISO8601.")
    booking.add_argument("--end", default="", help="Optional booking end datetime ISO8601.")
    booking.add_argument(
        "--unconfirmed",
        action="store_true",
        help="Mark booking as unconfirmed to validate policy block behavior.",
    )
    booking.add_argument(
        "--skip-crm",
        action="store_true",
        help="Book in Cal.com only and skip HubSpot sync.",
    )

    hubspot_booking = subparsers.add_parser("hubspot-booking", help="Write a booking event to HubSpot MCP only.")
    hubspot_booking.add_argument("--lead-id", default="", help="Optional fixed lead_id for traceability.")
    hubspot_booking.add_argument("--booking-id", default="", help="Optional fixed booking id.")
    hubspot_booking.add_argument("--slot-id", default="", help="Optional fixed slot id.")
    hubspot_booking.add_argument("--timezone", default="UTC")
    hubspot_booking.add_argument("--calendar-ref", default="", help="Optional booking reference URL.")
    hubspot_booking.add_argument(
        "--status",
        default="confirmed",
        help="Booking status written into CRM payload (default: confirmed).",
    )
    hubspot_booking.add_argument("--start", default="", help="Optional booking start datetime ISO8601.")
    hubspot_booking.add_argument("--end", default="", help="Optional booking end datetime ISO8601.")
    hubspot_booking.add_argument("--idempotency-key", default="", help="Optional fixed idempotency key.")
    hubspot_booking.add_argument(
        "--unconfirmed",
        action="store_true",
        help="Mark booking payload as unconfirmed.",
    )

    hubspot_tools = subparsers.add_parser("hubspot-tools", help="List available remote HubSpot MCP tools.")
    hubspot_tools.add_argument(
        "--strict",
        action="store_true",
        help="Fail when tool readiness check is not satisfied.",
    )

    return parser


def main() -> None:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "email":
        asyncio.run(run_email(args))
        return
    if args.command == "sms":
        asyncio.run(run_sms(args))
        return
    if args.command == "booking-sync":
        asyncio.run(run_booking_sync(args))
        return
    if args.command == "hubspot-booking":
        asyncio.run(run_hubspot_booking(args))
        return
    if args.command == "hubspot-tools":
        asyncio.run(run_hubspot_tools(args))
        if getattr(args, "strict", False):
            hubspot = build_hubspot_service()
            readiness = asyncio.run(hubspot.verify_tool_readiness())
            if not readiness.get("ready", False):
                raise SystemExit(f"HubSpot MCP readiness failed: {json.dumps(readiness)}")
        return
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
