"""Minimal graph state models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LeadGraphState(BaseModel):
    # Implements: FR-14
    # Workflow: lead_intake_and_enrichment.md
    # Schema: session_state.md
    # API: orchestration_api.md
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    company_id: str
    current_stage: str
    message_context: dict = Field(default_factory=dict)
    enrichment_refs: list[str] = Field(default_factory=list)
    policy_flags: list[str] = Field(default_factory=list)
    pending_actions: list[dict] = Field(default_factory=list)


class ReplyGraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    current_stage: str
    message_context: dict = Field(default_factory=dict)
    policy_flags: list[str] = Field(default_factory=list)
    pending_actions: list[dict] = Field(default_factory=list)


class SchedulingGraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    current_stage: str
    timezone: str | None = None
    pending_actions: list[dict] = Field(default_factory=list)
    policy_flags: list[str] = Field(default_factory=list)

