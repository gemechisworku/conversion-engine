"""Calendar tool wrappers."""

from __future__ import annotations

from agent.services.calendar.calcom_client import CalComService, book_and_sync_crm
from agent.services.calendar.schemas import AvailabilityRequest, BookingRequest, BookingResult, CalendarSlot, LinkedBookingResult
from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.observability.events import log_tool_end, log_tool_error, log_tool_start


def resolve_timezone(*, explicit_timezone: str | None, fallback_timezone: str = "UTC") -> str:
    return (explicit_timezone or "").strip() or fallback_timezone


async def get_calendar_slots(*, service: CalComService, request: AvailabilityRequest) -> list[CalendarSlot]:
    run_id = log_tool_start(
        trace_id=request.trace_id,
        tool_name="get_calendar_slots",
        lead_id=request.lead_id,
        input_data=request.model_dump(mode="json"),
    )
    try:
        result = await service.get_available_slots(request)
        log_tool_end(
            trace_id=request.trace_id,
            run_id=run_id,
            tool_name="get_calendar_slots",
            lead_id=request.lead_id,
            output_data={"slot_count": len(result)},
            status="success",
        )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=request.trace_id,
            run_id=run_id,
            tool_name="get_calendar_slots",
            lead_id=request.lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise


def propose_slots(*, slots: list[CalendarSlot], limit: int = 3) -> list[CalendarSlot]:
    return slots[: max(1, limit)]


async def book_discovery_call(*, service: CalComService, request: BookingRequest) -> BookingResult:
    run_id = log_tool_start(
        trace_id=request.trace_id,
        tool_name="book_discovery_call",
        lead_id=request.lead_id,
        input_data=request.model_dump(mode="json"),
    )
    try:
        result = await service.book_discovery_call(request)
        if result.succeeded:
            log_tool_end(
                trace_id=request.trace_id,
                run_id=run_id,
                tool_name="book_discovery_call",
                lead_id=request.lead_id,
                output_data=result.model_dump(mode="json"),
                status="success",
            )
        else:
            error_message = result.error.error_message if result.error else "Booking failed."
            retryable = bool(result.error.retryable) if result.error else False
            log_tool_error(
                trace_id=request.trace_id,
                run_id=run_id,
                tool_name="book_discovery_call",
                lead_id=request.lead_id,
                error={"type": "BookingFailed", "message": error_message, "retryable": retryable},
            )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=request.trace_id,
            run_id=run_id,
            tool_name="book_discovery_call",
            lead_id=request.lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise


async def book_and_sync(
    *,
    lead_id: str,
    request: BookingRequest,
    calcom_service: CalComService,
    hubspot_service: HubSpotMCPService,
) -> LinkedBookingResult:
    run_id = log_tool_start(
        trace_id=request.trace_id,
        tool_name="book_and_sync",
        lead_id=lead_id,
        input_data=request.model_dump(mode="json"),
    )
    try:
        result = await book_and_sync_crm(
            lead_id=lead_id,
            booking_request=request,
            calcom_service=calcom_service,
            hubspot_service=hubspot_service,
        )
        if result.booking.succeeded:
            log_tool_end(
                trace_id=request.trace_id,
                run_id=run_id,
                tool_name="book_and_sync",
                lead_id=lead_id,
                output_data=result.model_dump(mode="json"),
                status="success",
            )
        else:
            message = result.booking.error.error_message if result.booking.error else "Booking sync failed."
            retryable = bool(result.booking.error.retryable) if result.booking.error else False
            log_tool_error(
                trace_id=request.trace_id,
                run_id=run_id,
                tool_name="book_and_sync",
                lead_id=lead_id,
                error={"type": "BookingSyncFailed", "message": message, "retryable": retryable},
            )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=request.trace_id,
            run_id=run_id,
            tool_name="book_and_sync",
            lead_id=lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise
