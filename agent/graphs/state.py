"""Minimal graph state models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class LeadGraphState(BaseModel):
    # Implements: FR-14
    # Workflow: lead_intake_and_enrichment.md
    # Schema: session_state.md
    # API: orchestration_api.md
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    company_id: str | None = None
    current_stage: str
    next_best_action: str = "enrich"
    current_objective: str = "process_lead"
    message_context: dict = Field(default_factory=dict)
    enrichment_refs: list[str] = Field(default_factory=list)
    brief_refs: list[str] = Field(default_factory=list)
    kb_refs: list[str] = Field(default_factory=list)
    policy_flags: list[str] = Field(default_factory=list)
    pending_actions: list[dict] = Field(default_factory=list)
    handoff_required: bool = False
    last_compacted_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReplyGraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    current_stage: str
    conversation_state_id: str | None = None
    current_channel: str = "email"
    message_context: dict = Field(default_factory=dict)
    last_inbound_message_id: str | None = None
    last_outbound_message_id: str | None = None
    last_customer_intent: str = "unknown"
    last_customer_sentiment: str = "uncertain"
    qualification_status: str = "unknown"
    open_questions: list[dict] = Field(default_factory=list)
    objections: list[dict] = Field(default_factory=list)
    scheduling_context: dict = Field(default_factory=lambda: {"booking_status": "none"})
    policy_flags: list[str] = Field(default_factory=list)
    pending_actions: list[dict] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SchedulingGraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    current_stage: str
    timezone: str | None = None
    booking_status: str = "none"
    slot_id: str | None = None
    confirmed_by_prospect: bool = False
    pending_actions: list[dict] = Field(default_factory=list)
    policy_flags: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
