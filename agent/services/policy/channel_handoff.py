"""Centralized channel handoff decisions and scheduling CTA formatting."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from agent.services.common.schemas import PolicyDecision
from agent.services.policy.channel_policy import LeadChannelState, can_use_sms


class ChannelHandoffDecision(BaseModel):
    """Normalized channel decision shared across orchestration handlers."""

    lead_id: str
    requested_channel: str
    resolved_channel: Literal["email", "sms"]
    policy: PolicyDecision
    reason: str
    allowed: bool


def decide_channel_handoff(
    *,
    lead_id: str,
    requested_channel: str,
    lead_state: LeadChannelState,
    trace_id: str,
) -> ChannelHandoffDecision:
    # Implements: FR-10, FR-16
    # Workflow: scheduling_and_booking.md
    # Schema: policy_decision.md
    # API: policy_api.md
    normalized = (requested_channel or "").strip().lower()
    if normalized not in {"email", "sms"}:
        policy = PolicyDecision(
            policy_type="channel_policy",
            decision="blocked",
            reason=f"Unsupported channel '{requested_channel}'.",
            trace_id=trace_id,
            lead_id=lead_id,
        )
        return ChannelHandoffDecision(
            lead_id=lead_id,
            requested_channel=requested_channel,
            resolved_channel="email",
            policy=policy,
            reason=policy.reason,
            allowed=False,
        )
    if normalized == "email":
        policy = PolicyDecision(
            policy_type="channel_policy",
            decision="pass",
            reason="Email remains the default channel.",
            trace_id=trace_id,
            lead_id=lead_id,
        )
        return ChannelHandoffDecision(
            lead_id=lead_id,
            requested_channel="email",
            resolved_channel="email",
            policy=policy,
            reason=policy.reason,
            allowed=True,
        )
    policy = can_use_sms(lead_state=lead_state, trace_id=trace_id)
    return ChannelHandoffDecision(
        lead_id=lead_id,
        requested_channel="sms",
        resolved_channel="sms" if policy.is_allowed else "email",
        policy=policy,
        reason=policy.reason,
        allowed=policy.is_allowed,
    )


def build_scheduling_cta(*, channel: str, scheduling_portal_url: str) -> str:
    """Render a concise booking CTA tuned to channel constraints."""
    normalized = (channel or "").strip().lower()
    link = scheduling_portal_url.strip()
    if normalized == "sms":
        return f"Book a slot here: {link}"
    return f"You can book directly here: {link}"


def append_scheduling_cta(*, content: str, channel: str, scheduling_portal_url: str) -> str:
    """Append scheduling CTA once; do nothing if URL already present."""
    body = (content or "").strip()
    link = scheduling_portal_url.strip()
    if not body:
        return build_scheduling_cta(channel=channel, scheduling_portal_url=link)
    if link in body:
        return body
    cta = build_scheduling_cta(channel=channel, scheduling_portal_url=link)
    return f"{body}\n\n{cta}"
