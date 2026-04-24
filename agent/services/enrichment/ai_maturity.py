"""AI maturity scoring from enrichment signals."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.enrichment.schemas import AIMaturityScore, EnrichmentArtifact, WeightedSignal


def score_ai_maturity(*, company_id: str, artifact: EnrichmentArtifact) -> AIMaturityScore:
    # Implements: FR-3
    # Workflow: lead_intake_and_enrichment.md
    # Schema: ai_maturity_score.md
    # API: scoring_api.md
    signals: list[WeightedSignal] = []
    numeric_score = 0.0
    evidential_confidences: list[float] = []

    jobs_summary = _summary_dict(artifact.signals.get("job_posts"))
    ai_roles = _as_int(jobs_summary.get("ai_adjacent_role_count"))
    eng_roles = _as_int(jobs_summary.get("engineering_role_count"))
    if ai_roles >= 3:
        numeric_score += 1.5
        signals.append(
            WeightedSignal(
                signal_type="ai_adjacent_roles",
                weight="high",
                summary=f"{ai_roles} AI-adjacent roles publicly listed.",
                evidence_refs=["jobs_signal"],
            )
        )
        evidential_confidences.append(float(artifact.signals["job_posts"].confidence))
    elif ai_roles > 0:
        numeric_score += 0.75
        signals.append(
            WeightedSignal(
                signal_type="ai_adjacent_roles",
                weight="medium",
                summary=f"{ai_roles} AI-adjacent role(s) observed.",
                evidence_refs=["jobs_signal"],
            )
        )
        evidential_confidences.append(float(artifact.signals["job_posts"].confidence))

    crunchbase_summary = _summary_dict(artifact.signals.get("crunchbase"))
    funding_round = _as_str(crunchbase_summary.get("funding_round"))
    if funding_round:
        if funding_round.lower().startswith("series"):
            numeric_score += 0.75
        else:
            numeric_score += 0.5
        signals.append(
            WeightedSignal(
                signal_type="funding_signal",
                weight="medium",
                summary=f"Funding event detected ({funding_round}).",
                evidence_refs=["crunchbase_signal"],
            )
        )
        evidential_confidences.append(float(artifact.signals["crunchbase"].confidence))

    leadership_summary = _summary_dict(artifact.signals.get("leadership_changes"))
    role_name = _as_str(leadership_summary.get("role_name"))
    if role_name and any(token in role_name.lower() for token in ("cto", "vp", "engineering", "ai")):
        numeric_score += 0.5
        signals.append(
            WeightedSignal(
                signal_type="leadership_change",
                weight="medium",
                summary=f"Leadership transition detected ({role_name}).",
                evidence_refs=["leadership_signal"],
            )
        )
        evidential_confidences.append(float(artifact.signals["leadership_changes"].confidence))

    layoffs_summary = _summary_dict(artifact.signals.get("layoffs"))
    affected_percent = _as_float(layoffs_summary.get("affected_percent"))
    if affected_percent >= 20:
        numeric_score -= 0.5
        signals.append(
            WeightedSignal(
                signal_type="layoff_pressure",
                weight="medium",
                summary=f"Layoff signal indicates pressure ({affected_percent:.1f}% affected).",
                evidence_refs=["layoffs_signal"],
            )
        )
        evidential_confidences.append(float(artifact.signals["layoffs"].confidence))

    if eng_roles >= 8 and ai_roles >= 1:
        numeric_score += 0.5
        signals.append(
            WeightedSignal(
                signal_type="engineering_scale",
                weight="high",
                summary=f"Engineering hiring scale ({eng_roles} roles) with AI adjacency.",
                evidence_refs=["jobs_signal"],
            )
        )

    tech_stack = [str(item).lower() for item in _as_list(crunchbase_summary.get("tech_stack"))]
    ai_tech = [item for item in tech_stack if any(token in item for token in ("openai", "machine learning", "ml", "ai", "tensorflow", "pytorch", "databricks"))]
    if ai_tech:
        numeric_score += 1.0
        signals.append(
            WeightedSignal(
                signal_type="public_ai_or_data_stack",
                weight="high",
                summary=f"Public technology profile includes AI/data tooling: {', '.join(ai_tech[:3])}.",
                evidence_refs=["crunchbase_signal"],
            )
        )
        evidential_confidences.append(float(artifact.signals["crunchbase"].confidence))

    score = int(round(max(0.0, min(3.0, numeric_score))))
    confidence = _confidence(evidential_confidences=evidential_confidences, signal_count=len(signals))
    risk_notes: list[str] = []
    if len(signals) < 2:
        risk_notes.append("AI maturity score uses limited public evidence; soften claims.")
    if confidence < 0.6:
        risk_notes.append("Low confidence: prefer exploratory phrasing over assertions.")
    if confidence >= 0.75:
        risk_notes.append("Phrasing may state observed public signals directly.")
    elif confidence >= 0.55:
        risk_notes.append("Phrasing should frame maturity as a likely pattern, not a fact.")
    else:
        risk_notes.append("Phrasing should explicitly say public evidence is limited.")

    return AIMaturityScore(
        score_id=f"score_{uuid4().hex[:10]}",
        company_id=company_id,
        score=score,
        confidence=confidence,
        signals=signals,
        risk_notes=risk_notes,
    )


async def score_ai_maturity_with_llm(
    *,
    company_id: str,
    artifact: EnrichmentArtifact,
    llm: OpenRouterJSONClient | None,
) -> AIMaturityScore:
    deterministic = score_ai_maturity(company_id=company_id, artifact=artifact)
    if llm is None or not llm.configured:
        return deterministic
    candidate = await llm.generate_model(
        system_prompt=(
            "You are the AI Maturity Scorer. Apply the required 0-3 scoring rubric. "
            "High-weight inputs: AI-adjacent roles, public AI/data stack, engineering scale with AI adjacency. "
            "Medium-weight inputs: recent funding, recent CTO/VP Engineering hire, layoffs/cost pressure. "
            "Use confidence-sensitive phrasing and never infer strong maturity from weak evidence."
        ),
        user_payload={
            "required_schema": AIMaturityScore.model_json_schema(),
            "deterministic_candidate": deterministic.model_dump(mode="json"),
            "normalized_evidence": artifact.model_dump(mode="json"),
        },
        response_model=AIMaturityScore,
    )
    if not isinstance(candidate, AIMaturityScore):
        return deterministic
    if candidate.company_id != company_id:
        return deterministic
    candidate.score = int(max(0, min(3, candidate.score)))
    candidate.confidence = float(max(0.0, min(1.0, candidate.confidence)))
    if not candidate.signals:
        return deterministic
    return candidate


def _summary_dict(snapshot: Any) -> dict[str, Any]:
    if snapshot is None:
        return {}
    summary = getattr(snapshot, "summary", None)
    return summary if isinstance(summary, dict) else {}


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _confidence(*, evidential_confidences: list[float], signal_count: int) -> float:
    if not evidential_confidences:
        return 0.35
    baseline = sum(evidential_confidences) / len(evidential_confidences)
    if signal_count >= 4:
        baseline += 0.1
    elif signal_count == 1:
        baseline -= 0.1
    return float(max(0.3, min(0.95, round(baseline, 2))))
