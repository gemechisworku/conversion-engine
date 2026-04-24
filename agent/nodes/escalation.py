"""Escalation marker node (Phase 5 — observability hook for human handoff paths)."""

from __future__ import annotations

from agent.services.observability.events import log_processing_step


def escalation_event_node(*, lead_id: str, trace_id: str | None, reason_code: str) -> None:
    log_processing_step(
        component="nodes.escalation",
        step="escalation.marked",
        message="Escalation path recorded at node boundary",
        lead_id=lead_id,
        trace_id=trace_id,
        reason_code=reason_code,
    )
