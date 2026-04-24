"""Scheduling orchestration entry."""

from __future__ import annotations

from agent.graphs.scheduling_langgraph import SchedulingGraphDeps, invoke_scheduling_graph
from agent.graphs.state import SchedulingGraphState
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
    return await invoke_scheduling_graph(
        deps=SchedulingGraphDeps(calcom=services["calcom"], hubspot=services["hubspot"]),
        state=state,
        request=request,
    )
