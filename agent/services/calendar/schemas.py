"""Cal.com scheduling contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from agent.services.common.schemas import ErrorEnvelope
from agent.services.crm.schemas import CRMWriteResult


class CalendarSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str
    start_at: datetime
    end_at: datetime


class AvailabilityRequest(BaseModel):
    # Implements: FR-11
    # Workflow: scheduling_and_booking.md
    # Schema: booking_event.md
    # API: scheduling_api.md
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    trace_id: str
    timezone: str
    window_start: datetime
    window_end: datetime


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    trace_id: str
    slot_id: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    prospect_email: str
    prospect_name: str | None = None
    confirmed_by_prospect: bool
    idempotency_key: str


class BookingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking_id: str | None = None
    lead_id: str
    slot_id: str
    status: str
    timezone: str | None = None
    calendar_ref: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    confirmed_by_prospect: bool = False
    error: ErrorEnvelope | None = None
    raw_response: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.status == "confirmed"


class LinkedBookingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking: BookingResult
    crm_write: CRMWriteResult | None = None

