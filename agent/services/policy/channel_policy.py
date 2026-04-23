"""Channel eligibility policy checks."""

from __future__ import annotations

from pydantic import BaseModel

from agent.services.common.schemas import PolicyDecision


class LeadChannelState(BaseModel):
    """Minimal channel-warmth context for SMS policy checks."""

    lead_id: str
    has_prior_email_reply: bool = False
    explicit_warm_status: bool = False
    has_recent_inbound_sms: bool = False


def can_use_sms(*, lead_state: LeadChannelState, trace_id: str) -> PolicyDecision:
    # Implements: FR-10, FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: policy_decision.md
    # API: policy_api.md
    if lead_state.explicit_warm_status or lead_state.has_prior_email_reply or lead_state.has_recent_inbound_sms:
        return PolicyDecision(
            policy_type="channel_policy",
            decision="pass",
            reason="Lead is warm; SMS is allowed.",
            trace_id=trace_id,
            lead_id=lead_state.lead_id,
        )
    return PolicyDecision(
        policy_type="channel_policy",
        decision="blocked",
        reason="SMS is blocked for cold leads.",
        trace_id=trace_id,
        lead_id=lead_state.lead_id,
    )

