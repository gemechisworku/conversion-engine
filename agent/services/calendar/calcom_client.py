"""Cal.com client and booking-to-CRM linkage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.calendar.schemas import (
    AvailabilityRequest,
    BookingRequest,
    BookingResult,
    CalendarSlot,
    LinkedBookingResult,
)
from agent.services.common.schemas import ErrorEnvelope
from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.crm.schemas import CRMBookingPayload
from agent.services.observability.events import log_trace_event
from agent.services.policy.outbound_policy import OutboundPolicyService


class CalComService:
    # Implements: FR-11
    # Workflow: scheduling_and_booking.md
    # Schema: booking_event.md
    # API: scheduling_api.md
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

    async def get_available_slots(self, request: AvailabilityRequest) -> list[CalendarSlot]:
        self._settings.require("calcom_api_key")
        selector = self._resolve_event_selector()
        url = f"{self._settings.calcom_api_url.rstrip('/')}/slots"
        response, raw = await self._request_with_retry(
            method="GET",
            url=url,
            headers=self._headers(
                idempotency_key=f"slots:{request.lead_id}:{request.window_start.isoformat()}",
                api_version="2024-09-04",
            ),
            params={
                "start": self._to_utc_iso(request.window_start),
                "end": self._to_utc_iso(request.window_end),
                "timeZone": request.timezone,
                "format": "range",
                **selector,
            },
        )
        if response.status_code >= 400:
            error = ErrorEnvelope(
                error_code="SOURCE_UNAVAILABLE",
                error_message=f"Cal.com slots lookup failed with HTTP {response.status_code}.",
                retryable=response.status_code >= 500,
                details={"response": raw},
            )
            log_trace_event(
                event_type="calendar_slots_failed",
                trace_id=request.trace_id,
                lead_id=request.lead_id,
                status="failure",
                payload={"timezone": request.timezone},
                error=error.model_dump(),
            )
            raise RuntimeError(f"Cal.com slots lookup failed with HTTP {response.status_code}.")

        slots_data = raw.get("data", {}) if isinstance(raw.get("data"), dict) else {}
        slots: list[CalendarSlot] = []
        for day_slots in slots_data.values():
            if not isinstance(day_slots, list):
                continue
            for entry in day_slots:
                if not isinstance(entry, dict):
                    continue
                start_at = self._parse_dt(entry.get("start") or entry.get("start_at"))
                end_at = self._parse_dt(entry.get("end") or entry.get("end_at"))
                if not start_at or not end_at:
                    continue
                slot_id = str(entry.get("slot_id") or entry.get("id") or start_at.isoformat()).strip()
                slots.append(CalendarSlot(slot_id=slot_id, start_at=start_at, end_at=end_at))
        log_trace_event(
            event_type="calendar_slots_loaded",
            trace_id=request.trace_id,
            lead_id=request.lead_id,
            status="success",
            payload={"slot_count": len(slots), "timezone": request.timezone},
        )
        return slots

    async def book_discovery_call(self, request: BookingRequest) -> BookingResult:
        if not request.confirmed_by_prospect:
            error = ErrorEnvelope(
                error_code="POLICY_BLOCKED",
                error_message="Booking blocked: prospect confirmation is required.",
                retryable=False,
            )
            return BookingResult(
                lead_id=request.lead_id,
                slot_id=request.slot_id,
                status="failed",
                timezone=request.timezone,
                confirmed_by_prospect=False,
                error=error,
            )

        self._settings.require("calcom_api_key")
        selector = self._resolve_event_selector()
        decisions = self._policy_service.check_email_send(trace_id=request.trace_id, lead_id=request.lead_id)
        blocked = next((decision for decision in decisions if not decision.is_allowed), None)
        if blocked:
            error = ErrorEnvelope(
                error_code="POLICY_BLOCKED",
                error_message=blocked.reason,
                retryable=False,
                details={"policy_type": blocked.policy_type},
            )
            return BookingResult(
                lead_id=request.lead_id,
                slot_id=request.slot_id,
                status="failed",
                timezone=request.timezone,
                confirmed_by_prospect=True,
                error=error,
            )

        payload: dict[str, Any] = {
            "start": self._to_utc_iso(request.starts_at),
            "attendee": {
                "email": request.prospect_email,
                "timeZone": request.timezone,
                "name": self._resolve_attendee_name(request.prospect_name),
            },
            "metadata": {
                "lead_id": request.lead_id,
                "slot_id": request.slot_id,
                "trace_id": request.trace_id,
            },
            **selector,
        }

        response, raw = await self._request_with_retry(
            method="POST",
            url=f"{self._settings.calcom_api_url.rstrip('/')}/bookings",
            headers=self._headers(idempotency_key=request.idempotency_key, api_version="2026-02-25"),
            json=payload,
        )
        if response.status_code >= 400:
            error = ErrorEnvelope(
                error_code="BOOKING_FAILED",
                error_message=f"Cal.com returned HTTP {response.status_code}.",
                retryable=response.status_code >= 500,
                details={"response": raw},
            )
            return BookingResult(
                lead_id=request.lead_id,
                slot_id=request.slot_id,
                status="failed",
                timezone=request.timezone,
                confirmed_by_prospect=True,
                error=error,
                raw_response=raw,
            )

        status = str(raw.get("data", {}).get("status") or raw.get("status") or "confirmed")
        if status.lower() in {"failure", "failed"}:
            error = ErrorEnvelope(
                error_code="BOOKING_FAILED",
                error_message="Cal.com booking failed.",
                retryable=False,
                details={"response": raw},
            )
            return BookingResult(
                lead_id=request.lead_id,
                slot_id=request.slot_id,
                status="failed",
                timezone=request.timezone,
                confirmed_by_prospect=True,
                error=error,
                raw_response=raw,
            )

        data = raw.get("data", {}) if isinstance(raw.get("data"), dict) else raw
        booking_id = str(data.get("booking_id") or data.get("uid") or data.get("id") or "").strip() or None
        calendar_ref = str(data.get("booking_url") or data.get("location") or data.get("calendar_ref") or "").strip() or None
        result = BookingResult(
            booking_id=booking_id,
            lead_id=request.lead_id,
            slot_id=request.slot_id,
            status="confirmed",
            timezone=request.timezone,
            calendar_ref=calendar_ref,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            confirmed_by_prospect=True,
            raw_response=raw,
        )
        log_trace_event(
            event_type="booking_confirmed",
            trace_id=request.trace_id,
            lead_id=request.lead_id,
            status="success",
            payload={"booking_id": booking_id, "slot_id": request.slot_id},
        )
        return result

    async def _request_with_retry(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[httpx.Response, dict[str, Any]]:
        attempt = 0
        last_error: Exception | None = None
        while attempt <= self._max_retries:
            attempt += 1
            try:
                response = await self._request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params,
                )
                if response.is_success:
                    return response, self._safe_json(response)
                if response.status_code >= 500 and attempt <= self._max_retries:
                    continue
                return response, self._safe_json(response)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt <= self._max_retries:
                    continue
                raise
        raise RuntimeError(f"Unexpected calendar retry loop failure: {last_error}")

    async def _request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.request(method, url, headers=headers, json=json, params=params)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.request(method, url, headers=headers, json=json, params=params)

    def _headers(self, *, idempotency_key: str, api_version: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.calcom_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "cal-api-version": api_version,
        }

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            parsed = response.json()
            return parsed if isinstance(parsed, dict) else {"payload": parsed}
        except ValueError:
            return {}

    @staticmethod
    def _parse_dt(value: Any):
        if value is None:
            return None
        try:
            text = str(value).replace("Z", "+00:00")
            from datetime import datetime

            return datetime.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _to_utc_iso(value: datetime) -> str:
        dt = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _coerce_event_type_id(value: str) -> int | str:
        text = str(value).strip()
        return int(text) if text.isdigit() else text

    def _resolve_event_selector(self) -> dict[str, Any]:
        event_type_id = str(self._settings.calcom_event_type_id or "").strip()
        if event_type_id:
            return {"eventTypeId": self._coerce_event_type_id(event_type_id)}

        event_type_slug = str(self._settings.calcom_event_type_slug or "").strip()
        username = str(self._settings.calcom_username or "").strip()
        if event_type_slug and username:
            return {"eventTypeSlug": event_type_slug, "username": username}

        raise ValueError(
            "Missing Cal.com event selector. Configure either CALCOM_EVENT_TYPE_ID "
            "or CALCOM_EVENT_TYPE_SLUG with CALCOM_USERNAME."
        )

    @staticmethod
    def _resolve_attendee_name(name: str | None) -> str:
        cleaned = (name or "").strip()
        return cleaned if cleaned else "Prospect"


async def book_and_sync_crm(
    *,
    lead_id: str,
    booking_request: BookingRequest,
    calcom_service: CalComService,
    hubspot_service: HubSpotMCPService,
    company_name: str | None = None,
    company_domain: str | None = None,
) -> LinkedBookingResult:
    # Implements: FR-11, FR-12
    # Workflow: scheduling_and_booking.md
    # Schema: booking_event.md
    # API: scheduling_api.md
    booking = await calcom_service.book_discovery_call(booking_request)
    if not booking.succeeded:
        return LinkedBookingResult(booking=booking, crm_write=None)

    booking_payload = CRMBookingPayload(
        lead_id=lead_id,
        booking_id=booking.booking_id or "",
        slot_id=booking.slot_id,
        status=booking.status,
        timezone=booking.timezone,
        calendar_ref=booking.calendar_ref,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        confirmed_by_prospect=booking.confirmed_by_prospect,
        company_name=company_name,
        company_domain=company_domain,
    )
    crm_write = await hubspot_service.record_booking(
        lead_id=lead_id,
        booking=booking_payload,
        trace_id=booking_request.trace_id,
        idempotency_key=f"{lead_id}:{booking_request.slot_id}",
    )
    return LinkedBookingResult(booking=booking, crm_write=crm_write)
