"""ICP classification node (Phase 5 — thin service delegate)."""

from __future__ import annotations

from agent.config.settings import Settings
from agent.services.enrichment.icp_classifier import classify_icp, classify_icp_with_care
from agent.services.enrichment.schemas import AIMaturityScore, EnrichmentArtifact, ICPClassification


async def classification_node(
    *,
    artifact: EnrichmentArtifact,
    ai_maturity: AIMaturityScore,
    settings: Settings | None,
    llm: object | None,
    trace_id: str | None,
    lead_id: str,
) -> ICPClassification:
    if settings is not None and llm is not None:
        return await classify_icp_with_care(
            artifact=artifact,
            ai_maturity=ai_maturity,
            llm=llm,
            settings=settings,
            trace_id=trace_id,
            lead_id=lead_id,
        )
    return classify_icp(artifact=artifact, ai_maturity=ai_maturity)
