"""Email service data contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.services.common.schemas import ErrorEnvelope


class OutboundEmailRequest(BaseModel):
    # Implements: FR-7, FR-8, FR-10, FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: outreach_draft.md
    # API: outreach_api.md
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    draft_id: str
    review_id: str
    review_status: Literal["approved", "approved_with_edits", "pending", "rejected", "blocked_by_policy"] = "approved"
    trace_id: str
    idempotency_key: str
    to_email: str
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    from_email: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensure_message_body(self) -> "OutboundEmailRequest":
        if not self.text_body and not self.html_body:
            raise ValueError("Either text_body or html_body is required.")
        return self


class InboundEmailEvent(BaseModel):
    # Implements: FR-9, FR-10, FR-15
    # Workflow: reply_handling.md
    # Schema: conversation_state.md
    # API: orchestration_api.md
    model_config = ConfigDict(extra="forbid")

    provider: Literal["resend"] = "resend"
    event_type: Literal["reply", "bounce", "delivery_failure", "unknown", "malformed"]
    provider_message_id: str | None = None
    from_email: str | None = None
    to_email: str | None = None
    subject: str | None = None
    text_body: str | None = None
    html_body: str | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rfc_message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    raw_payload_ref: str
    error: ErrorEnvelope | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
