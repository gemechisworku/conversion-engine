"""Outreach draft node (Phase 5 — delegates to outreach_flow)."""

from __future__ import annotations

from agent.services.email.schemas import OutboundEmailRequest
from agent.services.outreach.outreach_flow import OutreachFlowDeps, run_outreach_draft_only


async def outreach_draft_node(
    *,
    deps: OutreachFlowDeps,
    lead_id: str,
    trace_id: str,
    idempotency_key: str,
    to_email: str,
    company_name: str,
    variant: str = "cold_email",
    brief_id: str | None = None,
    gap_brief_id: str | None = None,
) -> OutboundEmailRequest:
    return await run_outreach_draft_only(
        deps,
        lead_id=lead_id,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        to_email=to_email,
        company_name=company_name,
        variant=variant,
        brief_id=brief_id,
        gap_brief_id=gap_brief_id,
    )
