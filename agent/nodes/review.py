"""Tone / claim review node (Phase 5 — delegates to tone_claim_reviewer)."""

from __future__ import annotations

from agent.config.settings import Settings
from agent.services.email.schemas import OutboundEmailRequest
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.outreach.tone_claim_reviewer import ToneClaimReviewRecord, run_tone_claim_review
from agent.services.policy.outbound_policy import OutboundPolicyService


async def review_outreach_node(
    *,
    settings: Settings,
    policy: OutboundPolicyService,
    llm: OpenRouterJSONClient | None,
    outbound: OutboundEmailRequest,
    hiring_signal_brief: dict,
    competitor_gap_brief: dict,
    trace_id: str | None,
    lead_id: str | None,
) -> ToneClaimReviewRecord:
    return await run_tone_claim_review(
        settings=settings,
        policy=policy,
        llm=llm,
        outbound=outbound,
        hiring_signal_brief=hiring_signal_brief,
        competitor_gap_brief=competitor_gap_brief,
        trace_id=trace_id,
        lead_id=lead_id,
    )
