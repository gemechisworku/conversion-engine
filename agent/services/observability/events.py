"""Trace logging helpers."""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger("agent.observability")


def log_trace_event(
    *,
    event_type: str,
    trace_id: str,
    lead_id: str | None,
    status: str,
    payload: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    # Implements: FR-15
    # Workflow: outreach_generation_and_review.md
    # Schema: trace_event.md
    # API: observability_api.md
    LOGGER.info(
        "trace_event type=%s trace_id=%s lead_id=%s status=%s payload=%s error=%s",
        event_type,
        trace_id,
        lead_id,
        status,
        payload or {},
        error,
    )

