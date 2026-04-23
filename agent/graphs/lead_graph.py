"""Lead intake orchestration entry."""

from __future__ import annotations

from agent.graphs.state import LeadGraphState
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.tools.enrichment_tools import enrich_company


async def run_lead_intake(
    *,
    state: LeadGraphState,
    company_name: str,
    company_domain: str,
    services: dict,
) -> tuple[LeadGraphState, EnrichmentArtifact]:
    # Implements: FR-1, FR-2
    # Workflow: lead_intake_and_enrichment.md
    # Schema: session_state.md
    # API: orchestration_api.md
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
    updated_state = state.model_copy(
        update={
            "current_stage": "brief_ready",
            "enrichment_refs": [artifact.company_id],
        }
    )
    return updated_state, artifact

