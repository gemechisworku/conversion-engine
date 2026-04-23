"""Shared schema contracts for deterministic services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    # Implements: FR-15, FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: trace_event.md
    # API: orchestration_api.md
    error_code: str
    error_message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ProviderSendResult(BaseModel):
    provider: str
    provider_message_id: str | None = None
    accepted: bool
    raw_status: str
    error: ErrorEnvelope | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    policy_type: Literal[
        "kill_switch",
        "sink_routing",
        "bench_commitment",
        "claim_validation",
        "escalation",
        "channel_policy",
    ]
    decision: Literal["pass", "fail", "blocked", "escalate"]
    reason: str
    trace_id: str
    lead_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_allowed(self) -> bool:
        return self.decision == "pass"

