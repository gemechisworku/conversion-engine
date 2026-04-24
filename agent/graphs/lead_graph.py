"""Lead intake orchestration entry."""

from __future__ import annotations

from contextlib import nullcontext

from agent.config.settings import Settings
from agent.graphs.state import LeadGraphState
from agent.graphs.transitions import validate_lead_transition
from agent.services.enrichment.ai_maturity import score_ai_maturity_with_llm
from agent.services.enrichment.hiring_brief import build_hiring_signal_brief_with_llm
from agent.services.enrichment.icp_classifier import classify_icp, classify_icp_with_care
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.services.observability.langfuse_llm import langfuse_workflow_span
from agent.tools.enrichment_tools import enrich_company


def _lf_span(settings: Settings | None, *, trace_id: str, lead_id: str, name: str):
    if isinstance(settings, Settings) and trace_id.strip():
        return langfuse_workflow_span(settings, trace_id=trace_id, lead_id=lead_id, name=name)
    return nullcontext()


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
    settings_obj = services.get("settings")
    llm_client = services.get("llm")
    raw_trace = services.get("trace_id")
    trace_hint = str(raw_trace).strip() if raw_trace is not None else ""
    trace_for_edges = trace_hint or f"lead_intake:{state.lead_id}"
    lf_settings = settings_obj if isinstance(settings_obj, Settings) else None
    lf_trace = trace_hint or None

    artifact = await enrich_company(
        company_id=state.company_id,
        company_name=company_name,
        company_domain=company_domain,
        crunchbase=services["crunchbase"],
        jobs=services["jobs"],
        layoffs=services["layoffs"],
        leadership=services["leadership"],
        merger=services["merger"],
        lf_settings=lf_settings,
        lf_trace_id=lf_trace,
        lf_lead_id=state.lead_id,
    )
    with _lf_span(
        lf_settings,
        trace_id=trace_hint,
        lead_id=state.lead_id,
        name="enrichment.ai_maturity",
    ):
        ai_maturity = await score_ai_maturity_with_llm(
            company_id=state.company_id,
            artifact=artifact,
            llm=llm_client,
        )
    with _lf_span(
        lf_settings,
        trace_id=trace_hint,
        lead_id=state.lead_id,
        name="enrichment.icp_classification",
    ):
        if isinstance(settings_obj, Settings) and llm_client is not None:
            classification = await classify_icp_with_care(
                artifact=artifact,
                ai_maturity=ai_maturity,
                llm=llm_client,
                settings=settings_obj,
                trace_id=trace_hint or None,
                lead_id=state.lead_id,
            )
        else:
            classification = classify_icp(artifact=artifact, ai_maturity=ai_maturity)
    with _lf_span(
        lf_settings,
        trace_id=trace_hint,
        lead_id=state.lead_id,
        name="enrichment.competitor_gap_brief",
    ):
        gap_brief = await services["competitor_gap"].build_brief(
            lead_id=state.lead_id,
            company_id=state.company_id,
            artifact=artifact,
            ai_maturity=ai_maturity,
        )
    with _lf_span(
        lf_settings,
        trace_id=trace_hint,
        lead_id=state.lead_id,
        name="enrichment.hiring_signal_brief",
    ):
        hiring_brief = await build_hiring_signal_brief_with_llm(
            lead_id=state.lead_id,
            company_id=state.company_id,
            artifact=artifact,
            ai_maturity=ai_maturity,
            classification=classification,
            llm=llm_client,
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
        repo = services["state_repo"]
        repo.append_evidence_edge(
            lead_id=state.lead_id,
            trace_id=trace_for_edges,
            edge_type="brief.hiring_signal",
            brief_id=hiring_brief.brief_id,
            payload={"brief_id": hiring_brief.brief_id, "kind": "hiring_signal_brief"},
        )
        repo.append_evidence_edge(
            lead_id=state.lead_id,
            trace_id=trace_for_edges,
            edge_type="brief.competitor_gap",
            brief_id=gap_brief.gap_brief_id,
            payload={"gap_brief_id": gap_brief.gap_brief_id, "kind": "competitor_gap_brief"},
        )
        repo.append_evidence_edge(
            lead_id=state.lead_id,
            trace_id=trace_for_edges,
            edge_type="score.ai_maturity",
            brief_id=None,
            source_ref=ai_maturity.score_id,
            payload={"score_id": ai_maturity.score_id, "kind": "ai_maturity_score"},
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
