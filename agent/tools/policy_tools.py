"""Policy tool wrappers."""

from __future__ import annotations

from agent.services.common.schemas import PolicyDecision
from agent.services.policy.channel_policy import LeadChannelState, can_use_sms
from agent.services.policy.outbound_policy import OutboundPolicyService


def check_kill_switch(*, service: OutboundPolicyService, trace_id: str, lead_id: str) -> PolicyDecision:
    return service.check_kill_switch(trace_id=trace_id, lead_id=lead_id)


def check_sink_routing(*, service: OutboundPolicyService, trace_id: str, lead_id: str) -> PolicyDecision:
    return service.check_sink_routing(trace_id=trace_id, lead_id=lead_id)


def check_sms_channel(*, lead_state: LeadChannelState, trace_id: str) -> PolicyDecision:
    return can_use_sms(lead_state=lead_state, trace_id=trace_id)


def check_bench_commitment(
    *,
    service: OutboundPolicyService,
    trace_id: str,
    lead_id: str,
    message: str,
    bench_verified: bool,
) -> PolicyDecision:
    return service.check_bench_commitment(
        trace_id=trace_id,
        lead_id=lead_id,
        message=message,
        bench_verified=bench_verified,
    )


def require_human_handoff(
    *,
    service: OutboundPolicyService,
    trace_id: str,
    lead_id: str,
    reason: str,
) -> PolicyDecision:
    return service.check_escalation_trigger(
        trace_id=trace_id,
        lead_id=lead_id,
        needs_human_handoff=True,
        reason=reason,
    )
