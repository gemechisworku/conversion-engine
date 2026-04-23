"""Enrichment node."""

from __future__ import annotations

from agent.graphs.lead_graph import run_lead_intake
from agent.graphs.state import LeadGraphState
from agent.services.enrichment.schemas import EnrichmentArtifact


async def enrichment_node(
    *,
    state: LeadGraphState,
    company_name: str,
    company_domain: str,
    services: dict,
) -> tuple[LeadGraphState, EnrichmentArtifact]:
    return await run_lead_intake(
        state=state,
        company_name=company_name,
        company_domain=company_domain,
        services=services,
    )

