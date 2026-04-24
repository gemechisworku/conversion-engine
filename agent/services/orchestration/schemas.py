"""Orchestration API contracts for local runtime handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent.services.common.schemas import ErrorEnvelope


class ResponseEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    trace_id: str
    status: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: ErrorEnvelope | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LeadProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    company_id: str
    source: str = "crunchbase"
    priority: str = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)


class LeadReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    lead_id: str
    channel: str
    message_id: str
    content: str
    subject: str | None = None
    from_email: str | None = None
    from_number: str | None = None
    company_name: str | None = None
    company_domain: str | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LeadAdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    lead_id: str
    from_state: str
    to_state: str
    reason: str


class LeadEscalationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    lead_id: str
    reason_code: str
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
