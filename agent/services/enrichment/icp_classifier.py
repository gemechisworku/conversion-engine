"""ICP classification with Tenacious precedence rules plus optional LLM adjudication (FR-5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent.config.settings import Settings
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.enrichment.sales_playbook import load_icp_definition
from agent.services.enrichment.schemas import AIMaturityScore, EnrichmentArtifact, ICPClassification
from agent.services.observability.events import log_processing_step

SEGMENT_1 = "segment_1_series_a_b"
SEGMENT_2 = "segment_2_mid_market_restructure"
SEGMENT_3 = "segment_3_leadership_transition"
SEGMENT_4 = "segment_4_specialized_capability"
_SEGMENTS = {SEGMENT_1, SEGMENT_2, SEGMENT_3, SEGMENT_4}


class _ICPLLMAdjudication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agree_with_heuristic: bool = True
    primary_segment: str
    alternate_segment: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    abstain: bool = False
    rationale: list[str] = Field(default_factory=list)


def classify_icp(*, artifact: EnrichmentArtifact, ai_maturity: AIMaturityScore) -> ICPClassification:
    # Implements: FR-5
    # Workflow: lead_intake_and_enrichment.md
    # Schema: hiring_signal_brief.md
    # API: scoring_api.md
    """Deterministic classifier using `seed/icp_definition.md` precedence and abstention rules."""
    flags = _extract_icp_flags(artifact=artifact, ai_maturity=ai_maturity)
    scores = _segment_scores(artifact=artifact, ai_maturity=ai_maturity, flags=flags)
    primary, alternate, confidence, rationale = _apply_precedence_and_confidence(
        artifact=artifact, ai_maturity=ai_maturity, flags=flags, scores=scores
    )
    abstain = confidence < 0.6 or primary is None
    resolved_primary = "abstain" if abstain or primary is None else primary
    resolved_alt = None if abstain else alternate
    return ICPClassification(
        classification_id=f"class_{uuid4().hex[:10]}",
        primary_segment=resolved_primary,
        alternate_segment=resolved_alt,
        confidence=round(confidence, 2) if not abstain else round(min(confidence, 0.55), 2),
        abstain=abstain,
        rationale=rationale,
    )


async def classify_icp_with_care(
    *,
    artifact: EnrichmentArtifact,
    ai_maturity: AIMaturityScore,
    llm: OpenRouterJSONClient | None,
    settings: Settings | None,
    trace_id: str | None = None,
    lead_id: str | None = None,
) -> ICPClassification:
    """Heuristic classification plus optional OpenRouter adjudication against full ICP doc (conservative merge)."""
    heuristic = classify_icp(artifact=artifact, ai_maturity=ai_maturity)
    if llm is None or not llm.configured or settings is None:
        return heuristic

    icp_doc = load_icp_definition(settings)
    if not icp_doc.strip():
        log_processing_step(
            component="enrichment.icp",
            step="icp.llm.skip",
            message="ICP adjudication skipped: tenacious_sales_data icp_definition not found",
            trace_id=trace_id,
            lead_id=lead_id,
        )
        return heuristic

    flags = _extract_icp_flags(artifact=artifact, ai_maturity=ai_maturity)
    adjudication = await llm.generate_model(
        system_prompt=(
            "You adjudicate B2B lead ICP classification for Tenacious Consulting. "
            "The user JSON contains: (1) the official ICP_DEFINITION markdown, "
            "(2) structured SIGNAL_FLAGS from public research only, "
            "(3) a HEURISTIC_CLASSIFICATION already computed using precedence rules. "
            "Your job: confirm or conservatively correct. If evidence is thin, set abstain=true. "
            "primary_segment MUST be exactly one of: "
            "segment_1_series_a_b, segment_2_mid_market_restructure, "
            "segment_3_leadership_transition, segment_4_specialized_capability, or abstain. "
            "When abstain is true, primary_segment must be the string 'abstain'. "
            "Never invent funding dates, layoffs, or leadership moves not present in SIGNAL_FLAGS."
        ),
        user_payload={
            "ICP_DEFINITION": icp_doc[:24_000],
            "SIGNAL_FLAGS": flags,
            "HEURISTIC_CLASSIFICATION": heuristic.model_dump(mode="json"),
            "AI_MATURITY": {"score": ai_maturity.score, "confidence": ai_maturity.confidence},
        },
        response_model=_ICPLLMAdjudication,
        trace_id=trace_id,
        lead_id=lead_id,
        purpose="icp.adjudication",
    )
    if adjudication is None:
        log_processing_step(
            component="enrichment.icp",
            step="icp.llm.fallback",
            message="ICP adjudication LLM returned null; using heuristic classification",
            trace_id=trace_id,
            lead_id=lead_id,
        )
        return heuristic

    merged = _merge_icp_adjudication(heuristic=heuristic, adj=adjudication)
    log_processing_step(
        component="enrichment.icp",
        step="icp.llm.merged",
        message="ICP classification merged after LLM adjudication",
        trace_id=trace_id,
        lead_id=lead_id,
        primary_segment=merged.primary_segment,
        abstain=merged.abstain,
        agree_with_heuristic=adjudication.agree_with_heuristic,
    )
    return merged


def _merge_icp_adjudication(*, heuristic: ICPClassification, adj: _ICPLLMAdjudication) -> ICPClassification:
    """Prefer conservative outcomes: any abstain or invalid segment falls back to heuristic or abstain."""
    primary = adj.primary_segment.strip()
    if primary not in _SEGMENTS and primary != "abstain":
        return heuristic
    if adj.abstain or primary == "abstain":
        return ICPClassification(
            classification_id=heuristic.classification_id,
            primary_segment="abstain",
            alternate_segment=None,
            confidence=min(heuristic.confidence, adj.confidence, 0.55),
            abstain=True,
            rationale=[*heuristic.rationale, *adj.rationale, "LLM adjudication selected abstention."],
        )
    if primary not in _SEGMENTS:
        return heuristic
    alt = adj.alternate_segment.strip() if adj.alternate_segment else None
    if alt is not None and alt not in _SEGMENTS:
        alt = heuristic.alternate_segment
    conf = min(0.95, max(heuristic.confidence, adj.confidence))
    if not adj.agree_with_heuristic and conf < 0.62:
        return ICPClassification(
            classification_id=heuristic.classification_id,
            primary_segment="abstain",
            alternate_segment=None,
            confidence=0.52,
            abstain=True,
            rationale=[*heuristic.rationale, *adj.rationale, "LLM disagreed with heuristic and confidence stayed low; abstaining."],
        )
    return ICPClassification(
        classification_id=heuristic.classification_id,
        primary_segment=primary,
        alternate_segment=alt,
        confidence=round(conf, 2),
        abstain=False,
        rationale=[*heuristic.rationale, *adj.rationale],
    )


def _extract_icp_flags(*, artifact: EnrichmentArtifact, ai_maturity: AIMaturityScore) -> dict[str, Any]:
    crunchbase = _summary_dict(artifact, "crunchbase")
    jobs = _summary_dict(artifact, "job_posts")
    layoffs = _summary_dict(artifact, "layoffs")
    leadership = _summary_dict(artifact, "leadership_changes")

    funding_round = _to_str(crunchbase.get("funding_round")).lower()
    funding_date = _parse_dt(_to_str(crunchbase.get("funding_date")))
    now = datetime.now(UTC)
    funding_age_days = (now - funding_date).days if funding_date else None
    funding_series_ab_180d = (
        funding_date is not None
        and funding_age_days is not None
        and funding_age_days <= 180
        and ("series a" in funding_round or "series b" in funding_round)
    )

    layoff_matched = bool(layoffs.get("matched"))
    layoff_date = _parse_dt(_to_str(layoffs.get("layoff_date")))
    layoff_age_days = (now - layoff_date).days if layoff_date else (0 if layoff_matched else None)
    layoff_within_120d = layoff_matched and (layoff_age_days is None or layoff_age_days <= 120)
    layoff_pct = _to_float(layoffs.get("affected_percent"))

    leadership_role = _to_str(leadership.get("role_name")).lower()
    leadership_date = _parse_dt(_to_str(leadership.get("date")))
    leadership_age = (now - leadership_date).days if leadership_date else None
    cto_vp_recent = bool(
        leadership.get("matched", True)
        and leadership_date
        and leadership_age is not None
        and leadership_age <= 90
        and ("cto" in leadership_role or "vp" in leadership_role or "chief technology" in leadership_role)
    )

    engineering_roles = _to_int(jobs.get("engineering_role_count"))
    ai_roles = _to_int(jobs.get("ai_adjacent_role_count"))
    role_titles = jobs.get("role_titles") if isinstance(jobs.get("role_titles"), list) else []
    titles_blob = " ".join(str(t) for t in role_titles).lower()
    specialist_keywords = (
        "ml platform",
        "machine learning",
        "agent",
        "mlops",
        "data contract",
        "ai platform",
        "llm",
    )
    specialist_title_hit = any(k in titles_blob for k in specialist_keywords)
    specialized_capability_signal = (ai_roles >= 2 and engineering_roles >= 5) or specialist_title_hit

    seg1_layoff_disqual = layoff_matched and layoff_pct >= 15 and layoff_age_days is not None and layoff_age_days <= 90

    return {
        "funding_series_ab_within_180d": funding_series_ab_180d,
        "funding_round_raw": crunchbase.get("funding_round"),
        "funding_age_days": funding_age_days,
        "layoff_matched": layoff_matched,
        "layoff_within_120d": layoff_within_120d,
        "layoff_affected_percent": layoff_pct,
        "segment_1_layoff_disqualifier_fired": seg1_layoff_disqual,
        "cto_or_vp_engineering_within_90d": cto_vp_recent,
        "engineering_role_count": engineering_roles,
        "ai_adjacent_role_count": ai_roles,
        "specialized_capability_signal": specialized_capability_signal,
        "ai_maturity_score": ai_maturity.score,
    }


def _segment_scores(
    *,
    artifact: EnrichmentArtifact,
    ai_maturity: AIMaturityScore,
    flags: dict[str, Any],
) -> dict[str, float]:
    scores: dict[str, float] = {SEGMENT_1: 0.0, SEGMENT_2: 0.0, SEGMENT_3: 0.0, SEGMENT_4: 0.0}
    crunchbase = _summary_dict(artifact, "crunchbase")
    jobs = _summary_dict(artifact, "job_posts")
    layoffs = _summary_dict(artifact, "layoffs")
    leadership = _summary_dict(artifact, "leadership_changes")

    funding_round = _to_str(crunchbase.get("funding_round")).lower()
    funding_date = _parse_dt(_to_str(crunchbase.get("funding_date")))
    if funding_date and (datetime.now(UTC) - funding_date).days <= 180:
        if funding_round.startswith("series a") or funding_round.startswith("series b"):
            scores[SEGMENT_1] += 0.7

    engineering_roles = _to_int(jobs.get("engineering_role_count"))
    ai_roles = _to_int(jobs.get("ai_adjacent_role_count"))
    if engineering_roles >= 5:
        scores[SEGMENT_1] += 0.25
    if ai_roles >= 2 and ai_maturity.score >= 2:
        scores[SEGMENT_4] += 0.7

    if bool(layoffs.get("matched")):
        scores[SEGMENT_2] += 0.6
    if _to_float(layoffs.get("affected_percent")) >= 15:
        scores[SEGMENT_2] += 0.2

    leadership_role = _to_str(leadership.get("role_name")).lower()
    leadership_date = _parse_dt(_to_str(leadership.get("date")))
    if leadership_date and (datetime.now(UTC) - leadership_date).days <= 90:
        if "cto" in leadership_role or "vp" in leadership_role:
            scores[SEGMENT_3] += 0.75

    if scores[SEGMENT_2] >= 0.6 and scores[SEGMENT_1] >= 0.6:
        scores[SEGMENT_2] += 0.2
    if scores[SEGMENT_3] >= 0.75:
        scores[SEGMENT_3] += 0.15
    return scores


def _apply_precedence_and_confidence(
    *,
    artifact: EnrichmentArtifact,
    ai_maturity: AIMaturityScore,
    flags: dict[str, Any],
    scores: dict[str, float],
) -> tuple[str | None, str | None, float, list[str]]:
    """Apply `icp_definition.md` classification order; confidence from rule strength + signal depth."""
    rationale: list[str] = []
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    # Order from seed/icp_definition.md "Classification rules"
    if flags["layoff_within_120d"] and flags["funding_series_ab_within_180d"]:
        rationale.append("Rule 1: layoff within 120d and Series A/B funding within 180d -> Segment 2 (cost pressure).")
        return SEGMENT_2, ranked[0][0] if ranked[0][0] != SEGMENT_2 else ranked[1][0], 0.82, rationale

    if flags["cto_or_vp_engineering_within_90d"]:
        rationale.append("Rule 2: CTO/VP Eng transition within 90d -> Segment 3.")
        alt = SEGMENT_1 if flags["funding_series_ab_within_180d"] else ranked[1][0]
        return SEGMENT_3, alt, 0.84, rationale

    if flags["specialized_capability_signal"] and ai_maturity.score >= 2:
        rationale.append("Rule 3: specialized public hiring/role signal and AI maturity >= 2 -> Segment 4.")
        return SEGMENT_4, ranked[1][0], 0.8, rationale

    if flags["funding_series_ab_within_180d"] and not flags["segment_1_layoff_disqualifier_fired"]:
        rationale.append("Rule 4: fresh Series A/B within 180d without layoff disqualifier -> Segment 1.")
        return SEGMENT_1, ranked[1][0], 0.78, rationale

    if flags["funding_series_ab_within_180d"] and flags["segment_1_layoff_disqualifier_fired"]:
        rationale.append("Segment 1 disqualified (material layoff); defaulting to Segment 2 posture.")
        return SEGMENT_2, SEGMENT_3, 0.72, rationale

    primary, primary_score = ranked[0]
    alternate, alternate_score = ranked[1]
    confidence = round(max(0.35, min(0.92, primary_score)), 2)
    rationale.append("Heuristic scores used; no strict precedence rule fully matched.")
    if confidence < 0.6:
        rationale.append("Confidence < 0.6 -> abstention per ICP definition.")
        return None, alternate, confidence, rationale
    return primary, alternate if alternate_score > 0.15 else None, confidence, rationale


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
