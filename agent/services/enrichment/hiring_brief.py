"""Build hiring_signal_brief from enrichment artifacts."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.services.enrichment.schemas import (
    AIMaturityScore,
    EnrichmentArtifact,
    HiringSignalBrief,
    ICPClassification,
    SignalBriefEntry,
)
from agent.services.enrichment.llm import OpenRouterJSONClient


def build_hiring_signal_brief(
    *,
    lead_id: str,
    company_id: str,
    artifact: EnrichmentArtifact,
    ai_maturity: AIMaturityScore,
    classification: ICPClassification,
) -> HiringSignalBrief:
    # Implements: FR-6
    # Workflow: lead_intake_and_enrichment.md
    # Schema: hiring_signal_brief.md
    # API: research_api.md
    signals: dict[str, SignalBriefEntry] = {
        "funding_event": _signal_entry(artifact=artifact, key="crunchbase", summary_key="funding_round"),
        "job_post_velocity": _job_signal_entry(artifact=artifact),
        "layoffs": _signal_entry(artifact=artifact, key="layoffs", summary_key="layoff_date"),
        "leadership_change": _signal_entry(artifact=artifact, key="leadership_changes", summary_key="role_name"),
        "tech_stack": _tech_stack_entry(artifact=artifact),
    }
    min_signal_confidence = min(entry.confidence for entry in signals.values()) if signals else 1.0
    should_soften = min_signal_confidence < 0.6 or ai_maturity.confidence < 0.6

    risk_notes = list(ai_maturity.risk_notes)
    if classification.abstain:
        risk_notes.append("Classification abstained due to low segment confidence.")
    if should_soften:
        risk_notes.append("Use confidence-softened phrasing in outreach.")

    return HiringSignalBrief(
        brief_id=f"brief_{uuid4().hex[:10]}",
        lead_id=lead_id,
        company_id=company_id,
        primary_segment_hypothesis=classification.primary_segment,
        alternate_segment_hypothesis=classification.alternate_segment,
        segment_confidence=classification.confidence,
        signals=signals,
        ai_maturity={
            "score": ai_maturity.score,
            "confidence": ai_maturity.confidence,
            "justification_refs": [signal.signal_type for signal in ai_maturity.signals],
            "signals": [signal.model_dump(mode="json") for signal in ai_maturity.signals],
        },
        bench_match={
            "status": artifact.bench_match_status or "partial_match",
            "confidence": 0.6,
            "required_skills": _required_skills(artifact=artifact),
            "available_skills": _available_skills(artifact=artifact),
            "notes": [],
        },
        research_hook={
            "summary": _research_hook(artifact=artifact, classification=classification),
            "confidence": round((ai_maturity.confidence + classification.confidence) / 2.0, 2),
        },
        language_guidance={
            "tone_mode": "assertive_but_softened" if should_soften else "direct_grounded",
            "allowed_claim_types": ["observed_hiring", "public_funding", "peer_pattern"],
            "disallowed_claim_types": ["guaranteed_capacity", "unsupported_benchmark_claim"],
            "must_soften": should_soften,
        },
        risk_notes=risk_notes,
    )


async def build_hiring_signal_brief_with_llm(
    *,
    lead_id: str,
    company_id: str,
    artifact: EnrichmentArtifact,
    ai_maturity: AIMaturityScore,
    classification: ICPClassification,
    llm: OpenRouterJSONClient | None,
) -> HiringSignalBrief:
    deterministic = build_hiring_signal_brief(
        lead_id=lead_id,
        company_id=company_id,
        artifact=artifact,
        ai_maturity=ai_maturity,
        classification=classification,
    )
    if llm is None or not llm.configured:
        return deterministic
    candidate = await llm.generate_model(
        system_prompt=(
            "You are the Hiring Signal Brief Generator. Produce a schema-valid hiring_signal_brief. "
            "Keep all factual claims grounded in evidence_refs. Use softened language when confidence is below 0.6. "
            "Do not invent funding, jobs, layoffs, leadership, tech-stack, or bench availability."
        ),
        user_payload={
            "required_schema": HiringSignalBrief.model_json_schema(),
            "deterministic_candidate": deterministic.model_dump(mode="json"),
            "normalized_evidence": artifact.model_dump(mode="json"),
            "ai_maturity": ai_maturity.model_dump(mode="json"),
            "classification": classification.model_dump(mode="json"),
        },
        response_model=HiringSignalBrief,
    )
    if not isinstance(candidate, HiringSignalBrief):
        return deterministic
    if candidate.lead_id != lead_id or candidate.company_id != company_id:
        return deterministic
    return candidate


def _summary_dict(*, artifact: EnrichmentArtifact, key: str) -> dict[str, Any]:
    snapshot = artifact.signals.get(key)
    if snapshot is None:
        return {}
    summary = snapshot.summary
    return summary if isinstance(summary, dict) else {}


def _signal_entry(*, artifact: EnrichmentArtifact, key: str, summary_key: str) -> SignalBriefEntry:
    snapshot = artifact.signals.get(key)
    if snapshot is None:
        return SignalBriefEntry(present=False, summary="No signal available.", confidence=0.2, evidence_refs=[])
    summary = _summary_dict(artifact=artifact, key=key)
    value = summary.get(summary_key)
    present = bool(value) if not isinstance(value, bool) else value
    return SignalBriefEntry(
        present=present,
        summary=str(value or "No strong public signal found."),
        confidence=float(snapshot.confidence),
        evidence_refs=[f"{key}_signal"],
    )


def _job_signal_entry(*, artifact: EnrichmentArtifact) -> SignalBriefEntry:
    snapshot = artifact.signals.get("job_posts")
    if snapshot is None:
        return SignalBriefEntry(present=False, summary="No job-post signal available.", confidence=0.2, evidence_refs=[])
    summary = _summary_dict(artifact=artifact, key="job_posts")
    engineering = int(summary.get("engineering_role_count") or 0)
    ai_adjacent = int(summary.get("ai_adjacent_role_count") or 0)
    present = engineering > 0
    text = f"{engineering} engineering roles, {ai_adjacent} AI-adjacent roles observed."
    return SignalBriefEntry(
        present=present,
        summary=text,
        confidence=float(snapshot.confidence),
        evidence_refs=["job_posts_signal"],
    )


def _tech_stack_entry(*, artifact: EnrichmentArtifact) -> SignalBriefEntry:
    stack = _summary_dict(artifact=artifact, key="tech_stack")
    technologies = stack.get("technologies", [])
    present = isinstance(technologies, list) and len(technologies) > 0
    summary = (
        f"Public technology profile includes: {', '.join(str(item) for item in technologies[:5])}."
        if present
        else "No strong public tech-stack signal."
    )
    confidence = float(artifact.signals.get("tech_stack").confidence if artifact.signals.get("tech_stack") else 0.3)
    return SignalBriefEntry(
        present=present,
        summary=summary,
        confidence=confidence,
        evidence_refs=["tech_stack_signal"] if present else [],
    )


def _required_skills(*, artifact: EnrichmentArtifact) -> list[str]:
    jobs = _summary_dict(artifact=artifact, key="job_posts")
    titles = jobs.get("role_titles", [])
    if not isinstance(titles, list):
        return []
    skills: set[str] = set()
    for title in titles[:10]:
        text = str(title).lower()
        if "python" in text:
            skills.add("python")
        if "data" in text:
            skills.add("data")
        if "ml" in text or "ai" in text:
            skills.add("ml")
    return sorted(skills)


def _available_skills(*, artifact: EnrichmentArtifact) -> list[str]:
    required = _required_skills(artifact=artifact)
    # SPEC-GAP: bench_summary integration is not yet represented in deterministic service contracts.
    return [skill for skill in required if skill in {"python", "data", "ml"}]


def _research_hook(*, artifact: EnrichmentArtifact, classification: ICPClassification) -> str:
    jobs = _summary_dict(artifact=artifact, key="job_posts")
    roles = int(jobs.get("engineering_role_count") or 0)
    if classification.abstain:
        return "Public signals are mixed; start with exploratory qualification."
    if roles >= 5:
        return "Public hiring and company trajectory suggest active engineering scale pressure."
    return "Public company signals suggest a potential fit worth validating in discovery."
