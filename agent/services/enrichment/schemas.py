"""Enrichment schemas for signal collection and merging."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

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


class WeightedSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: str
    weight: Literal["high", "medium", "low"]
    summary: str
    justification: str
    evidence_refs: list[str] = Field(default_factory=list)


class AIMaturityScore(BaseModel):
    # Implements: FR-3
    # Workflow: lead_intake_and_enrichment.md
    # Schema: ai_maturity_score.md
    # API: scoring_api.md
    model_config = ConfigDict(extra="forbid")

    score_id: str
    company_id: str
    score: int
    confidence: float
    signals: list[WeightedSignal] = Field(default_factory=list)
    confidence_rationale: str | None = None
    silent_company: bool = False
    risk_notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ICPClassification(BaseModel):
    # Implements: FR-5
    # Workflow: lead_intake_and_enrichment.md
    # Schema: hiring_signal_brief.md
    # API: scoring_api.md
    model_config = ConfigDict(extra="forbid")

    classification_id: str
    primary_segment: str
    alternate_segment: str | None = None
    confidence: float
    abstain: bool = False
    rationale: list[str] = Field(default_factory=list)


class SignalBriefEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    present: bool
    summary: str
    confidence: float
    evidence_refs: list[str] = Field(default_factory=list)


class HiringSignalBrief(BaseModel):
    # Implements: FR-6
    # Workflow: lead_intake_and_enrichment.md
    # Schema: hiring_signal_brief.md
    # API: research_api.md
    model_config = ConfigDict(extra="forbid")

    brief_id: str
    lead_id: str
    company_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    primary_segment_hypothesis: str | None = None
    alternate_segment_hypothesis: str | None = None
    segment_confidence: float = 0.0
    signals: dict[str, SignalBriefEntry]
    ai_maturity: dict[str, Any]
    bench_match: dict[str, Any]
    research_hook: dict[str, Any]
    language_guidance: dict[str, Any]
    risk_notes: list[str] = Field(default_factory=list)


class CompetitorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str
    reason_included: str
    ai_maturity_score: int
    confidence: float


class PracticeGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    practice: str
    confidence: float
    evidence_refs: list[str] = Field(default_factory=list)


class TopQuartilePractice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    practice: str
    evidence_refs: list[str] = Field(default_factory=list)


class CompetitorGapBrief(BaseModel):
    # Implements: FR-4
    # Workflow: lead_intake_and_enrichment.md
    # Schema: competitor_gap_brief.md
    # API: scoring_api.md
    model_config = ConfigDict(extra="forbid")

    gap_brief_id: str
    lead_id: str
    company_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    comparison_set: list[CompetitorRecord] = Field(default_factory=list)
    sector_percentile: float = 0.0
    top_quartile_practices: list[TopQuartilePractice] = Field(default_factory=list)
    missing_practices: list[PracticeGap] = Field(default_factory=list)
    language_guidance: dict[str, Any] = Field(
        default_factory=lambda: {"avoid_condescension": True, "frame_as_observation": True}
    )
    confidence: float = 0.0
    risk_notes: list[str] = Field(default_factory=list)


class Firmographics(BaseModel):
    # Implements: FR-2
    # Workflow: lead_intake_and_enrichment.md
    # Schema: evidence_record.md
    # API: research_api.md
    model_config = ConfigDict(extra="forbid")

    company_name: str | None = None
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    industries: list[str] = Field(default_factory=list)
    location: str | None = None
    region: str | None = None
    employee_count: str | None = None
    founded_date: str | None = None
    funding_rounds: str | None = None
    funding_total: str | None = None
    operating_status: str | None = None
    crunchbase_url: str | None = None


class EnrichmentBrief(BaseModel):
    # Implements: FR-2
    # Workflow: reply_handling.md
    # Schema: evidence_record.md
    # API: research_api.md
    model_config = ConfigDict(extra="forbid")

    brief_id: str
    lead_id: str
    company_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    matched: bool
    match_type: str
    matched_identifier: str | None = None
    match_confidence: float
    firmographics: Firmographics
    source_refs: list[SourceRef] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class ComplianceIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue: str
    count: int
    sample_product: str | None = None


class ComplianceBrief(BaseModel):
    # Implements: FR-2, FR-16
    # Workflow: reply_handling.md
    # Schema: evidence_record.md
    # API: research_api.md
    model_config = ConfigDict(extra="forbid")

    brief_id: str
    lead_id: str
    company_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    applicable: bool
    company_name: str | None = None
    lookback_days: int = 180
    complaint_count: int = 0
    top_issues: list[ComplianceIssue] = Field(default_factory=list)
    confidence: float = 0.0
    source_refs: list[SourceRef] = Field(default_factory=list)
    skipped_reason: str | None = None
    error: str | None = None
    risk_notes: list[str] = Field(default_factory=list)


class NewsBrief(BaseModel):
    # Implements: FR-2
    # Workflow: reply_handling.md
    # Schema: evidence_record.md
    # API: research_api.md
    model_config = ConfigDict(extra="forbid")

    brief_id: str
    lead_id: str
    company_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    found: bool
    source_type: Literal["filing", "news", "company_post", "unknown"] = "unknown"
    title: str | None = None
    url: str | None = None
    published_at: str | None = None
    snippet: str | None = None
    confidence: float = 0.0
    source_refs: list[SourceRef] = Field(default_factory=list)
    error: str | None = None
    risk_notes: list[str] = Field(default_factory=list)


class ActIIEnrichmentContext(BaseModel):
    # Implements: FR-2, FR-9
    # Workflow: reply_handling.md
    # Schema: conversation_state.md
    # API: orchestration_api.md
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    enrichment_brief: EnrichmentBrief
    compliance_brief: ComplianceBrief
    news_brief: NewsBrief
    artifact_paths: dict[str, str] = Field(default_factory=dict)
