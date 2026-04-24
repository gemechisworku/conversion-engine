"""Lead intake orchestration entry."""

from __future__ import annotations

from agent.graphs.state import LeadGraphState
from agent.graphs.transitions import validate_lead_transition
from agent.services.enrichment.ai_maturity import score_ai_maturity_with_llm
from agent.services.enrichment.hiring_brief import build_hiring_signal_brief_with_llm
from agent.services.enrichment.icp_classifier import classify_icp
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.tools.enrichment_tools import enrich_company


async def run_lead_intake(
    *,
    state: LeadGraphState,
    company_name: str,
    company_domain: str,
    services: dict,
) -> tuple[LeadGraphState, EnrichmentArtifact]:
    # Implements: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6
    # Workflow: lead_intake_and_enrichment.md
    # Schema: session_state.md
    # API: orchestration_api.md
    if not state.company_id:
        raise ValueError("company_id is required for lead intake enrichment.")
    artifact = await enrich_company(
        company_id=state.company_id,
        company_name=company_name,
        company_domain=company_domain,
        crunchbase=services["crunchbase"],
        jobs=services["jobs"],
        layoffs=services["layoffs"],
        leadership=services["leadership"],
        merger=services["merger"],
    )
    ai_maturity = await score_ai_maturity_with_llm(
        company_id=state.company_id,
        artifact=artifact,
        llm=services.get("llm"),
    )
    classification = classify_icp(artifact=artifact, ai_maturity=ai_maturity)
    gap_brief = await services["competitor_gap"].build_brief(
        lead_id=state.lead_id,
        company_id=state.company_id,
        artifact=artifact,
        ai_maturity=ai_maturity,
    )
    hiring_brief = await build_hiring_signal_brief_with_llm(
        lead_id=state.lead_id,
        company_id=state.company_id,
        artifact=artifact,
        ai_maturity=ai_maturity,
        classification=classification,
        llm=services.get("llm"),
    )
    if services.get("state_repo") is not None:
        services["state_repo"].cache_enrichment(
            lead_id=state.lead_id,
            company_id=state.company_id,
            artifact=artifact.model_dump(mode="json"),
        )
        services["state_repo"].upsert_briefs(
            lead_id=state.lead_id,
            hiring_signal_brief=hiring_brief.model_dump(mode="json"),
            competitor_gap_brief=gap_brief.model_dump(mode="json"),
            ai_maturity_score=ai_maturity.model_dump(mode="json"),
        )
        writer = services.get("artifact_writer")
        if writer is not None:
            writer.write_lead_briefs(
                lead_id=state.lead_id,
                hiring_signal_brief=hiring_brief.model_dump(mode="json"),
                competitor_gap_brief=gap_brief.model_dump(mode="json"),
                ai_maturity_score=ai_maturity.model_dump(mode="json"),
                enrichment_artifact=artifact.model_dump(mode="json"),
            )
    validate_lead_transition(from_state=state.current_stage, to_state="brief_ready")
    updated_state = state.model_copy(
        update={
            "current_stage": "brief_ready",
            "enrichment_refs": [artifact.company_id],
            "brief_refs": [hiring_brief.brief_id, gap_brief.gap_brief_id, ai_maturity.score_id],
            "next_best_action": "draft",
            "updated_at": hiring_brief.generated_at,
        }
    )
    return updated_state, artifact
