"""Scheduling node."""

from __future__ import annotations

from agent.graphs.scheduling_graph import run_scheduling
from agent.graphs.state import SchedulingGraphState
from agent.services.calendar.schemas import BookingRequest, LinkedBookingResult


async def scheduling_node(
    *,
    state: SchedulingGraphState,
    request: BookingRequest,
    services: dict,
) -> tuple[SchedulingGraphState, LinkedBookingResult]:
    return await run_scheduling(state=state, request=request, services=services)

