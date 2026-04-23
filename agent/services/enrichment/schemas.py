"""Enrichment schemas for signal collection and merging."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_url: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SignalSnapshot(BaseModel):
    # Implements: FR-2, FR-6
    # Workflow: lead_intake_and_enrichment.md
    # Schema: evidence_record.md
    # API: research_api.md
    model_config = ConfigDict(extra="forbid")

    summary: dict[str, Any] | str
    confidence: float
    source_refs: list[SourceRef] = Field(default_factory=list)


class EnrichmentArtifact(BaseModel):
    # Implements: FR-2, FR-6
    # Workflow: lead_intake_and_enrichment.md
    # Schema: hiring_signal_brief.md
    # API: research_api.md
    model_config = ConfigDict(extra="forbid")

    company_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    signals: dict[str, SignalSnapshot]
    merged_confidence: dict[str, float]
    bench_match_status: str | None = None
    brief_references: list[str] = Field(default_factory=list)

