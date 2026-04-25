"""AI maturity scoring from enrichment signals."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.services.enrichment.ai_maturity_inputs import (
    INPUT_AI_LEADERSHIP,
    INPUT_AI_ROLES,
    INPUT_EXEC_COMMENTARY,
    INPUT_GITHUB,
    INPUT_STACK,
    INPUT_STRATEGIC_COMMS,
    collect_ai_maturity_inputs,
)
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.enrichment.schemas import AIMaturityScore, EnrichmentArtifact, SignalSnapshot, WeightedSignal


def score_ai_maturity(*, company_id: str, artifact: EnrichmentArtifact) -> AIMaturityScore:
    # Implements: FR-3
    # Workflow: lead_intake_and_enrichment.md
    # Schema: ai_maturity_score.md
    # API: scoring_api.md
    collected = collect_ai_maturity_inputs(artifact=artifact)
    specs: list[tuple[str, str, float]] = [
        (INPUT_AI_ROLES, "high", 1.0),
        (INPUT_AI_LEADERSHIP, "high", 1.0),
        (INPUT_GITHUB, "medium", 0.6),
        (INPUT_EXEC_COMMENTARY, "medium", 0.6),
        (INPUT_STACK, "low", 0.3),
        (INPUT_STRATEGIC_COMMS, "low", 0.3),
    ]
    weighted_total = 0.0
    present_count = 0
    present_confidences: list[float] = []
    scored_signals: list[WeightedSignal] = []
    for signal_key, weight_label, weight_value in specs:
        snapshot = collected.get(signal_key) or SignalSnapshot(summary={"present": False}, confidence=0.3, source_refs=[])
        summary = _summary_dict(snapshot)
        present = bool(summary.get("present"))
        if present:
            weighted_total += weight_value
            present_count += 1
            present_confidences.append(float(snapshot.confidence))
        scored_signals.append(
            WeightedSignal(
                signal_type=signal_key,
                weight=weight_label,  # type: ignore[arg-type]
                summary=_signal_summary(signal_key=signal_key, snapshot=summary),
                justification=_signal_justification(signal_key=signal_key, snapshot=summary, present=present),
                evidence_refs=_evidence_refs(snapshot=snapshot, fallback=signal_key),
            )
        )

    silent_company = present_count == 0
    if silent_company:
        score = 0
        confidence = 0.25
        confidence_rationale = (
            "No qualifying public AI-maturity evidence was found. "
            "This is a low-confidence score and absence of evidence is not evidence of absence."
        )
    else:
        if weighted_total < 1.0:
            score = 1
        elif weighted_total < 2.2:
            score = 2
        else:
            score = 3
        avg_conf = sum(present_confidences) / max(1, len(present_confidences))
        coverage = present_count / len(specs)
        confidence = float(max(0.3, min(0.95, round(0.25 + (0.45 * avg_conf) + (0.30 * coverage), 2))))
        if score == 2 and present_count <= 2:
            confidence_rationale = "Mid score inferred from limited high-weight signals; confidence is constrained."
        elif score == 2 and present_count >= 4:
            confidence_rationale = "Mid score supported by multiple corroborating signals."
        elif score >= 3:
            confidence_rationale = "Score driven by multiple weighted signals with consistent public evidence."
        else:
            confidence_rationale = "Score is based on partial evidence and should be phrased as exploratory."

    risk_notes: list[str] = []
    if silent_company:
        risk_notes.append("No public AI-maturity signals found; absence is not proof of absence.")
    if confidence < 0.6:
        risk_notes.append("Low confidence: prefer exploratory phrasing over assertions.")
    elif confidence < 0.75:
        risk_notes.append("Moderate confidence: frame conclusions as likely patterns.")
    else:
        risk_notes.append("Higher confidence: observed public signals can be stated directly.")

    return AIMaturityScore(
        score_id=f"score_{uuid4().hex[:10]}",
        company_id=company_id,
        score=score,
        confidence=confidence,
        signals=scored_signals,
        confidence_rationale=confidence_rationale,
        silent_company=silent_company,
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
            "Use six weighted inputs only: high=(ai_adjacent_open_roles, named_ai_ml_leadership), "
            "medium=(github_org_activity, executive_commentary), low=(modern_data_ml_stack, strategic_communications). "
            "Return per-signal justifications, a separate confidence field, and explicit silent-company handling where score=0 "
            "with the note that absence of evidence is not evidence of absence."
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


def _signal_summary(*, signal_key: str, snapshot: dict[str, Any]) -> str:
    present = bool(snapshot.get("present"))
    if signal_key == INPUT_AI_ROLES:
        count = int(snapshot.get("ai_adjacent_role_count") or 0)
        return f"{count} AI-adjacent open role(s) detected." if present else "No AI-adjacent open roles detected."
    if signal_key == INPUT_AI_LEADERSHIP:
        role = str(snapshot.get("role_name") or "").strip()
        return f"Named AI/ML leadership found ({role})." if present else "No named AI/ML leadership detected."
    if signal_key == INPUT_GITHUB:
        orgs = snapshot.get("orgs") if isinstance(snapshot.get("orgs"), list) else []
        return f"Public GitHub org signal present ({', '.join(str(o) for o in orgs[:2])})." if present else "No public GitHub org activity signal detected."
    if signal_key == INPUT_EXEC_COMMENTARY:
        return "Executive commentary signal found in public material." if present else "No executive AI commentary signal found."
    if signal_key == INPUT_STACK:
        hits = snapshot.get("stack_hits") if isinstance(snapshot.get("stack_hits"), list) else []
        return f"Modern data/ML stack signals detected ({', '.join(str(h) for h in hits[:3])})." if present else "No modern data/ML stack signal found."
    if signal_key == INPUT_STRATEGIC_COMMS:
        return "Strategic AI-related communications signal detected." if present else "No strategic AI communications signal found."
    return "Signal processed."


def _signal_justification(*, signal_key: str, snapshot: dict[str, Any], present: bool) -> str:
    if signal_key == INPUT_AI_ROLES:
        count = int(snapshot.get("ai_adjacent_role_count") or 0)
        return (
            f"Public job-post evidence includes {count} AI-adjacent role(s), which is a high-weight indicator."
            if present
            else "No AI-adjacent openings were observed in public postings; this high-weight indicator is absent."
        )
    if signal_key == INPUT_AI_LEADERSHIP:
        role = str(snapshot.get("role_name") or "N/A").strip()
        return (
            f"A named AI/ML leadership role was observed ({role}), which is treated as a high-weight indicator."
            if present
            else "No named AI/ML leadership role was observed; this high-weight indicator is absent."
        )
    if signal_key == INPUT_GITHUB:
        return (
            "Public GitHub organization presence/activity signal was found and contributes medium weight."
            if present
            else "No clear public GitHub organization activity signal was found."
        )
    if signal_key == INPUT_EXEC_COMMENTARY:
        return (
            "Executive commentary mentioning AI/technology direction was found in public material."
            if present
            else "No verifiable executive commentary signal was found in public material."
        )
    if signal_key == INPUT_STACK:
        return (
            "Public stack evidence shows modern data/ML tooling, counted as a low-weight maturity indicator."
            if present
            else "No modern data/ML tooling signal was found in public stack evidence."
        )
    if signal_key == INPUT_STRATEGIC_COMMS:
        return (
            "Public strategic communications indicate AI-related initiative visibility (low weight)."
            if present
            else "No strategic AI communications signal was found in public sources."
        )
    return "Signal justification unavailable."


def _evidence_refs(*, snapshot: SignalSnapshot, fallback: str) -> list[str]:
    refs = [ref.source_name for ref in snapshot.source_refs if ref.source_name]
    return refs or [fallback]
