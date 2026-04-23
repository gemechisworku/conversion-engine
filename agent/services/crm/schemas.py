"""CRM service contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent.services.common.schemas import ErrorEnvelope


class CRMLeadPayload(BaseModel):
    # Implements: FR-12
    # Workflow: crm_sync.md
    # Schema: crm_event.md
    # API: crm_api.md
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    company_id: str
    company_name: str
    company_domain: str | None = None
    segment: str | None = None
    alternate_segment: str | None = None
    segment_confidence: float | None = None
    ai_maturity_score: int | None = None


class CRMEnrichmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    enrichment_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    funding_signal_summary: str | None = None
    job_velocity_summary: str | None = None
    layoffs_signal_summary: str | None = None
    leadership_signal_summary: str | None = None
    bench_match_status: str | None = None
    brief_references: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class CRMBookingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    booking_id: str
    slot_id: str
    status: str
    timezone: str | None = None
    calendar_ref: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    confirmed_by_prospect: bool = True


class CRMWriteResult(BaseModel):
    provider: str = "hubspot_mcp"
    status: str
    lead_id: str
    record_id: str | None = None
    event_id: str | None = None
    error: ErrorEnvelope | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.status in {"upserted", "event_recorded", "updated"}

