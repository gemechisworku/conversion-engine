"""ICP classification heuristics for the four Tenacious segments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent.services.enrichment.schemas import AIMaturityScore, EnrichmentArtifact, ICPClassification

SEGMENT_1 = "segment_1_series_a_b"
SEGMENT_2 = "segment_2_mid_market_restructure"
SEGMENT_3 = "segment_3_leadership_transition"
SEGMENT_4 = "segment_4_specialized_capability"


def classify_icp(*, artifact: EnrichmentArtifact, ai_maturity: AIMaturityScore) -> ICPClassification:
    # Implements: FR-5
    # Workflow: lead_intake_and_enrichment.md
    # Schema: hiring_signal_brief.md
    # API: scoring_api.md
    scores: dict[str, float] = {SEGMENT_1: 0.0, SEGMENT_2: 0.0, SEGMENT_3: 0.0, SEGMENT_4: 0.0}
    rationale: list[str] = []

    crunchbase = _summary_dict(artifact, "crunchbase")
    jobs = _summary_dict(artifact, "job_posts")
    layoffs = _summary_dict(artifact, "layoffs")
    leadership = _summary_dict(artifact, "leadership_changes")

    funding_round = _to_str(crunchbase.get("funding_round")).lower()
    funding_date = _parse_dt(_to_str(crunchbase.get("funding_date")))
    recent_funding = bool(funding_round.startswith("series a") or funding_round.startswith("series b"))
    if recent_funding and funding_date and (datetime.now(UTC) - funding_date).days <= 180:
        scores[SEGMENT_1] += 0.7
        rationale.append("Series A/B funding in last 180 days supports Segment 1.")

    engineering_roles = _to_int(jobs.get("engineering_role_count"))
    ai_roles = _to_int(jobs.get("ai_adjacent_role_count"))
    if engineering_roles >= 5:
        scores[SEGMENT_1] += 0.25
    if ai_roles >= 2 and ai_maturity.score >= 2:
        scores[SEGMENT_4] += 0.7
        rationale.append("AI-capability hiring signal with AI maturity >=2 supports Segment 4.")

    layoffs_matched = bool(layoffs.get("matched"))
    affected_percent = _to_float(layoffs.get("affected_percent"))
    if layoffs_matched:
        scores[SEGMENT_2] += 0.6
        rationale.append("Recent layoffs signal supports Segment 2.")
    if affected_percent >= 15:
        scores[SEGMENT_2] += 0.2

    leadership_role = _to_str(leadership.get("role_name")).lower()
    leadership_date = _parse_dt(_to_str(leadership.get("date")))
    leadership_recent = leadership_date and (datetime.now(UTC) - leadership_date).days <= 90
    if leadership_recent and ("cto" in leadership_role or "vp" in leadership_role):
        scores[SEGMENT_3] += 0.75
        rationale.append("Recent CTO/VP Eng transition supports Segment 3.")

    # Conflict priority rule from ICP definition.
    if scores[SEGMENT_2] >= 0.6 and scores[SEGMENT_1] >= 0.6:
        scores[SEGMENT_2] += 0.2
        rationale.append("Cost pressure dominates over fresh funding per ICP precedence.")
    if scores[SEGMENT_3] >= 0.75:
        scores[SEGMENT_3] += 0.15
        rationale.append("Leadership transition precedence boosts Segment 3.")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary_segment, primary_score = ranked[0]
    alternate_segment, alternate_score = ranked[1]
    confidence = round(max(0.3, min(0.95, primary_score)), 2)
    abstain = confidence < 0.6
    if abstain:
        rationale.append("Confidence < 0.6; abstention path required.")

    return ICPClassification(
        classification_id=f"class_{uuid4().hex[:10]}",
        primary_segment="abstain" if abstain else primary_segment,
        alternate_segment=alternate_segment if not abstain and alternate_score > 0 else None,
        confidence=confidence,
        abstain=abstain,
        rationale=rationale,
    )


def _summary_dict(artifact: EnrichmentArtifact, key: str) -> dict[str, Any]:
    snapshot = artifact.signals.get(key)
    if snapshot is None:
        return {}
    summary = snapshot.summary
    return summary if isinstance(summary, dict) else {}


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed

