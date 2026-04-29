"""Trace logging helpers."""

from __future__ import annotations

import logging
import os
from typing import Any

from .tracer import JsonlTracer

LOGGER = logging.getLogger("agent.observability")
_TRACER: JsonlTracer | None = None


def get_tracer() -> JsonlTracer:
    global _TRACER
    if _TRACER is None:
        path = os.environ.get("TRACE_LOG_PATH", "eval/trace_log.jsonl")
        _TRACER = JsonlTracer(output_path=path)
    return _TRACER


def log_processing_step(
    *,
    component: str,
    step: str,
    message: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Human-visible pipeline progress (stdout when logging is configured)."""
    log = logging.getLogger(f"agent.{component}")
    parts = [f"[{step}]", message]
    for key in sorted(fields):
        value = fields[key]
        if value is None or value == "":
            continue
        text = repr(value) if not isinstance(value, str) else value
        if len(text) > 200:
            text = text[:197] + "..."
        parts.append(f"{key}={text}")
    log.log(level, " ".join(parts))


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
    canonical_type = _to_canonical_event_type(event_type, status)
    tracer = get_tracer()
    tracer.log_event(
        trace_id=trace_id,
        event_type=canonical_type,
        lead_id=lead_id,
        input_data=payload or {},
        output_data=payload or {},
        metadata={
            "status": _normalize_status(status),
            "tool_name": str((payload or {}).get("tool_name") or ""),
        },
        error=error,
    )
    LOGGER.info(
        "trace_event type=%s trace_id=%s lead_id=%s status=%s payload=%s error=%s",
        event_type,
        trace_id,
        lead_id,
        status,
        payload or {},
        error,
    )


def log_graph_start(
    *,
    trace_id: str,
    graph_name: str,
    lead_id: str | None = None,
    company_id: str | None = None,
    session_id: str | None = None,
    parent_run_id: str | None = None,
    input_data: Any | None = None,
) -> dict[str, str | None]:
    return get_tracer().start_trace(
        trace_id=trace_id,
        parent_run_id=parent_run_id,
        graph_name=graph_name,
        lead_id=lead_id,
        company_id=company_id,
        session_id=session_id,
        input_data=input_data,
    )


def log_graph_end(
    *,
    trace_id: str,
    run_id: str | None,
    graph_name: str,
    lead_id: str | None = None,
    company_id: str | None = None,
    session_id: str | None = None,
    output_data: Any | None = None,
    status: str = "success",
    error: dict[str, Any] | None = None,
) -> None:
    if not run_id:
        return
    get_tracer().end_trace(
        trace_id=trace_id,
        run_id=run_id,
        graph_name=graph_name,
        lead_id=lead_id,
        company_id=company_id,
        session_id=session_id,
        output_data=output_data,
        status=_normalize_status(status),
        error=error,
    )


def log_node_start(
    *,
    trace_id: str | None,
    node_name: str,
    graph_name: str | None = None,
    lead_id: str | None = None,
    company_id: str | None = None,
    session_id: str | None = None,
    parent_run_id: str | None = None,
    input_data: Any | None = None,
) -> str | None:
    return get_tracer().log_node_start(
        trace_id=trace_id,
        node_name=node_name,
        graph_name=graph_name,
        lead_id=lead_id,
        company_id=company_id,
        session_id=session_id,
        parent_run_id=parent_run_id,
        input_data=input_data,
    )


def log_node_end(
    *,
    trace_id: str | None,
    run_id: str | None,
    node_name: str,
    graph_name: str | None = None,
    lead_id: str | None = None,
    company_id: str | None = None,
    session_id: str | None = None,
    output_data: Any | None = None,
    status: str = "success",
    error: dict[str, Any] | None = None,
) -> None:
    get_tracer().log_node_end(
        trace_id=trace_id,
        run_id=run_id,
        node_name=node_name,
        graph_name=graph_name,
        lead_id=lead_id,
        company_id=company_id,
        session_id=session_id,
        output_data=output_data,
        status=_normalize_status(status),
        error=error,
    )


def log_tool_start(
    *,
    trace_id: str | None,
    tool_name: str,
    lead_id: str | None = None,
    parent_run_id: str | None = None,
    input_data: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    return get_tracer().log_tool_start(
        trace_id=trace_id,
        tool_name=tool_name,
        lead_id=lead_id,
        parent_run_id=parent_run_id,
        input_data=input_data,
        metadata=metadata,
    )


def log_tool_end(
    *,
    trace_id: str | None,
    run_id: str | None,
    tool_name: str,
    lead_id: str | None = None,
    output_data: Any | None = None,
    status: str = "success",
    metadata: dict[str, Any] | None = None,
) -> None:
    get_tracer().log_tool_end(
        trace_id=trace_id,
        run_id=run_id,
        tool_name=tool_name,
        lead_id=lead_id,
        output_data=output_data,
        status=_normalize_status(status),
        metadata=metadata,
    )


def log_tool_error(
    *,
    trace_id: str | None,
    run_id: str | None,
    tool_name: str,
    lead_id: str | None = None,
    error: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> None:
    get_tracer().log_tool_error(
        trace_id=trace_id,
        run_id=run_id,
        tool_name=tool_name,
        lead_id=lead_id,
        error=error,
        metadata=metadata,
    )


def log_state_transition(
    *,
    trace_id: str | None,
    lead_id: str | None,
    state_before: Any,
    state_after: Any,
    metadata: dict[str, Any] | None = None,
) -> None:
    get_tracer().log_state_transition(
        trace_id=trace_id,
        lead_id=lead_id,
        state_before=state_before,
        state_after=state_after,
        metadata=metadata,
    )


def log_policy_decision(
    *,
    trace_id: str | None,
    lead_id: str | None,
    policy_input: Any,
    policy_output: Any,
    status: str,
) -> None:
    get_tracer().log_policy_decision(
        trace_id=trace_id,
        lead_id=lead_id,
        input_data=policy_input,
        output_data=policy_output,
        status=_normalize_status(status),
    )


def _to_canonical_event_type(event_type: str, status: str) -> str:
    text = (event_type or "").strip().lower()
    if text in {
        "graph_start",
        "graph_end",
        "node_start",
        "node_end",
        "agent_start",
        "agent_end",
        "subagent_start",
        "subagent_end",
        "llm_start",
        "llm_end",
        "tool_start",
        "tool_end",
        "tool_error",
        "state_transition",
        "policy_decision",
        "message_sent",
        "reply_received",
        "booking_created",
        "crm_updated",
        "error",
    }:
        return text
    if "reply_received" in text:
        return "reply_received"
    if "booking" in text and status == "success":
        return "booking_created"
    if "crm" in text and status == "success":
        return "crm_updated"
    if "send" in text and status == "success":
        return "message_sent"
    if "blocked" in text:
        return "policy_decision"
    if "failed" in text or status == "failure":
        return "error"
    return "agent_end"


def _normalize_status(status: str) -> str:
    clean = (status or "").strip().lower()
    if clean in {"success", "failure", "blocked", "skipped"}:
        return clean
    if clean in {"ok", "accepted", "pass"}:
        return "success"
    if clean in {"error", "failed"}:
        return "failure"
    return "success"

