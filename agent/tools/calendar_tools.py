"""Calendar tool wrappers."""

from __future__ import annotations

from agent.services.calendar.calcom_client import CalComService, book_and_sync_crm
from agent.services.calendar.schemas import AvailabilityRequest, BookingRequest, BookingResult, CalendarSlot, LinkedBookingResult
from agent.services.crm.hubspot_mcp import HubSpotMCPService


async def get_calendar_slots(*, service: CalComService, request: AvailabilityRequest) -> list[CalendarSlot]:
    return await service.get_available_slots(request)


async def book_discovery_call(*, service: CalComService, request: BookingRequest) -> BookingResult:
    return await service.book_discovery_call(request)


async def book_and_sync(
    *,
    lead_id: str,
    request: BookingRequest,
    calcom_service: CalComService,
    hubspot_service: HubSpotMCPService,
) -> LinkedBookingResult:
    return await book_and_sync_crm(
        lead_id=lead_id,
        booking_request=request,
        calcom_service=calcom_service,
        hubspot_service=hubspot_service,
    )

