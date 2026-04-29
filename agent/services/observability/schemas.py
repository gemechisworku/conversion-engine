"""Schema contracts for local JSONL trace events."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TraceEventType = Literal[
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
]

TraceStatus = Literal["success", "failure", "blocked", "skipped"]


class TraceMetadata(BaseModel):
    model: str | None = None
    provider: str | None = None
    tool_name: str | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    status: TraceStatus = "success"


class TraceError(BaseModel):
    type: str
    message: str
    retryable: bool = False


class TraceRecord(BaseModel):
    trace_id: str
    run_id: str
    parent_run_id: str | None = None
    event_id: str
    event_type: TraceEventType
    timestamp: str
    duration_ms: int = 0
    graph_name: str | None = None
    node_name: str | None = None
    agent_name: str | None = None
    subagent_name: str | None = None
    lead_id: str | None = None
    company_id: str | None = None
    session_id: str | None = None
    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    metadata: TraceMetadata = Field(default_factory=TraceMetadata)
    error: TraceError | None = None

