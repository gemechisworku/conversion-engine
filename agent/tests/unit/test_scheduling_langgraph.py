from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from agent.graphs.scheduling_langgraph import SchedulingGraphDeps, compile_scheduling_graph
from agent.graphs.state import SchedulingGraphState
from agent.services.calendar.schemas import BookingRequest, BookingResult, LinkedBookingResult
from agent.services.crm.schemas import CRMWriteResult


def _booking_request() -> BookingRequest:
    start = datetime.now(tz=UTC)
    return BookingRequest(
        lead_id="lead_sched",
        trace_id="trace_s",
        slot_id="slot_1",
        starts_at=start,
        ends_at=start + timedelta(minutes=15),
        timezone="UTC",
        prospect_email="p@example.com",
        prospect_name="Pat",
        confirmed_by_prospect=True,
        idempotency_key=f"idem_{uuid4().hex[:8]}",
    )


def test_scheduling_graph_invokes_book_then_transition() -> None:
    linked = LinkedBookingResult(
        booking=BookingResult(
            booking_id="bk_1",
            lead_id="lead_sched",
            slot_id="slot_1",
            status="confirmed",
            timezone="UTC",
            starts_at=datetime.now(tz=UTC),
            ends_at=datetime.now(tz=UTC),
        ),
        crm_write=CRMWriteResult(status="upserted", lead_id="lead_sched"),
    )
    calcom = object()
    hubspot = object()
    deps = SchedulingGraphDeps(calcom=calcom, hubspot=hubspot)  # type: ignore[arg-type]

    with patch("agent.graphs.scheduling_langgraph.book_and_sync_crm", new_callable=AsyncMock) as mock_book:
        mock_book.return_value = linked
        graph = compile_scheduling_graph(deps)
        state = SchedulingGraphState(lead_id="lead_sched", current_stage="scheduling")
        req = _booking_request()
        out = asyncio.run(
            graph.ainvoke(
                {
                    "scheduling_state": state.model_dump(mode="json"),
                    "booking_request": req.model_dump(mode="json"),
                    "errors": [],
                }
            )
        )
    mock_book.assert_awaited_once()
    assert out["updated_scheduling_state"]["current_stage"] == "booked"
