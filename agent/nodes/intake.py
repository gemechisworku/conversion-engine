"""Lead intake initialize (Phase 5 node — validates graph input)."""

from __future__ import annotations

from typing import Any

from agent.graphs.state import LeadGraphState
from agent.services.observability.events import log_processing_step


async def intake_initialize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Validate `lead_state` payload before enrichment (implementation_plan Phase 5)."""
    LeadGraphState.model_validate(state["lead_state"])
    log_processing_step(
        component="nodes.intake",
        step="intake.validated",
        message="Lead intake graph input validated",
        lead_id=state.get("lead_id"),
        trace_id=state.get("trace_id"),
    )
    return {}
