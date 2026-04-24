"""AI maturity scoring node (Phase 5 — thin service delegate)."""

from __future__ import annotations

from agent.services.enrichment.ai_maturity import score_ai_maturity_with_llm
from agent.services.enrichment.schemas import AIMaturityScore, EnrichmentArtifact


async def scoring_node(
    *,
    company_id: str,
    artifact: EnrichmentArtifact,
    llm: object | None,
) -> AIMaturityScore:
    return await score_ai_maturity_with_llm(company_id=company_id, artifact=artifact, llm=llm)
