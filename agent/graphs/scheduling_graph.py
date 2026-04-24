"""Scheduling orchestration entry."""

from __future__ import annotations

from agent.graphs.state import SchedulingGraphState
from agent.graphs.transitions import validate_lead_transition
from agent.services.calendar.calcom_client import book_and_sync_crm
from agent.services.calendar.schemas import BookingRequest, LinkedBookingResult


async def run_scheduling(
    *,
    state: SchedulingGraphState,
    request: BookingRequest,
    services: dict,
) -> tuple[SchedulingGraphState, LinkedBookingResult]:
    # Implements: FR-11, FR-12
    # Workflow: scheduling_and_booking.md
    # Schema: booking_event.md
    # API: scheduling_api.md
    linked = await book_and_sync_crm(
        lead_id=state.lead_id,
        booking_request=request,
        calcom_service=services["calcom"],
        hubspot_service=services["hubspot"],
    )
    next_stage = "booked" if linked.booking.succeeded else "scheduling"
    validate_lead_transition(from_state=state.current_stage, to_state=next_stage)
    updated = state.model_copy(update={"current_stage": next_stage})
    return updated, linked
