"""LangGraph orchestration: Cal.com booking with linked HubSpot sync, then stage transition."""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from agent.graphs.state import SchedulingGraphState
from agent.graphs.transitions import validate_lead_transition
from agent.services.calendar.calcom_client import CalComService, book_and_sync_crm
from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.calendar.schemas import BookingRequest, LinkedBookingResult
from agent.services.observability.events import log_processing_step


class SchedulingGraphLGState(TypedDict, total=False):
    # Implements: FR-11, FR-12
    # Workflow: scheduling_and_booking.md
    scheduling_state: dict[str, Any]
    booking_request: dict[str, Any]
    linked_result: dict[str, Any]
    updated_scheduling_state: dict[str, Any]
    errors: Annotated[list[str], operator.add]


@dataclass
class SchedulingGraphDeps:
    calcom: CalComService
    hubspot: HubSpotMCPService


def compile_scheduling_graph(deps: SchedulingGraphDeps):
    graph: StateGraph = StateGraph(SchedulingGraphLGState)

    async def book_node(state: SchedulingGraphLGState) -> dict[str, Any]:
        st = SchedulingGraphState.model_validate(state["scheduling_state"])
        request = BookingRequest.model_validate(state["booking_request"])
        log_processing_step(
            component="graphs.scheduling",
            step="book_and_sync.start",
            message="Cal.com book + HubSpot CRM linkage",
            lead_id=st.lead_id,
            trace_id=request.trace_id,
            slot_id=request.slot_id,
            idempotency_key=request.idempotency_key,
        )
        linked = await book_and_sync_crm(
            lead_id=st.lead_id,
            booking_request=request,
            calcom_service=deps.calcom,
            hubspot_service=deps.hubspot,
        )
        log_processing_step(
            component="graphs.scheduling",
            step="book_and_sync.done",
            message="Booking + CRM calls finished",
            lead_id=st.lead_id,
            trace_id=request.trace_id,
            booking_status=linked.booking.status,
            crm_write_status=linked.crm_write.status if linked.crm_write else None,
        )
        return {"linked_result": linked.model_dump(mode="json")}

    async def transition_node(state: SchedulingGraphLGState) -> dict[str, Any]:
        linked = LinkedBookingResult.model_validate(state["linked_result"])
        st = SchedulingGraphState.model_validate(state["scheduling_state"])
        next_stage = "booked" if linked.booking.succeeded else "scheduling"
        log_processing_step(
            component="graphs.scheduling",
            step="transition",
            message="Validating scheduling stage transition",
            lead_id=st.lead_id,
            from_stage=st.current_stage,
            to_stage=next_stage,
        )
        validate_lead_transition(from_state=st.current_stage, to_state=next_stage)
        updated = st.model_copy(update={"current_stage": next_stage})
        return {"updated_scheduling_state": updated.model_dump(mode="json")}

    graph.add_node("book_and_sync", book_node)
    graph.add_node("transition", transition_node)
    graph.set_entry_point("book_and_sync")
    graph.add_edge("book_and_sync", "transition")
    graph.add_edge("transition", END)
    return graph.compile()


async def invoke_scheduling_graph(
    *,
    deps: SchedulingGraphDeps,
    state: SchedulingGraphState,
    request: BookingRequest,
) -> tuple[SchedulingGraphState, LinkedBookingResult]:
    log_processing_step(
        component="graphs.scheduling",
        step="graph.invoke",
        message="Starting scheduling LangGraph (book_and_sync → transition)",
        lead_id=state.lead_id,
        trace_id=request.trace_id,
    )
    graph = compile_scheduling_graph(deps)
    initial: SchedulingGraphLGState = {
        "scheduling_state": state.model_dump(mode="json"),
        "booking_request": request.model_dump(mode="json"),
        "errors": [],
    }
    final = await graph.ainvoke(initial)
    linked = LinkedBookingResult.model_validate(final["linked_result"])
    log_processing_step(
        component="graphs.scheduling",
        step="graph.done",
        message="Scheduling LangGraph completed",
        lead_id=state.lead_id,
        trace_id=request.trace_id,
        booking_status=linked.booking.status,
    )
    return (SchedulingGraphState.model_validate(final["updated_scheduling_state"]), linked)
