"""SMS service data contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.services.common.schemas import ErrorEnvelope
from agent.services.policy.channel_policy import LeadChannelState


class OutboundSMSRequest(BaseModel):
    # Implements: FR-9, FR-10, FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: conversation_state.md
    # API: outreach_api.md
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    draft_id: str
    review_id: str
    review_status: Literal["approved", "approved_with_edits", "pending", "rejected", "blocked_by_policy"] = "approved"
    trace_id: str
    idempotency_key: str
    to_number: str
    message: str
    from_shortcode: str | None = None
    lead_channel_state: LeadChannelState
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboundSMSEvent(BaseModel):
    # Implements: FR-9, FR-10, FR-15
    # Workflow: reply_handling.md
    # Schema: conversation_state.md
    # API: orchestration_api.md
    model_config = ConfigDict(extra="forbid")

    provider: Literal["africastalking"] = "africastalking"
    event_type: Literal[
        "inbound_sms",
        "delivery_report",
        "command_stop",
        "command_help",
        "command_unsub",
        "unknown",
        "malformed",
    ]
    provider_message_id: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    text: str | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_payload_ref: str
    error: ErrorEnvelope | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
