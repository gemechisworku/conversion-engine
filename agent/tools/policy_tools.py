"""Policy tool wrappers."""

from __future__ import annotations

from agent.services.common.schemas import PolicyDecision
from agent.services.observability.events import log_policy_decision
from agent.services.policy.channel_policy import LeadChannelState, can_use_sms
from agent.services.policy.outbound_policy import OutboundPolicyService


def check_kill_switch(*, service: OutboundPolicyService, trace_id: str, lead_id: str) -> PolicyDecision:
    decision = service.check_kill_switch(trace_id=trace_id, lead_id=lead_id)
    log_policy_decision(
        trace_id=trace_id,
        lead_id=lead_id,
        policy_input={"policy_type": "kill_switch"},
        policy_output=decision.model_dump(mode="json"),
        status="blocked" if not decision.is_allowed else "success",
    )
    return decision


def check_sink_routing(*, service: OutboundPolicyService, trace_id: str, lead_id: str) -> PolicyDecision:
    decision = service.check_sink_routing(trace_id=trace_id, lead_id=lead_id)
    log_policy_decision(
        trace_id=trace_id,
        lead_id=lead_id,
        policy_input={"policy_type": "sink_routing"},
        policy_output=decision.model_dump(mode="json"),
        status="blocked" if not decision.is_allowed else "success",
    )
    return decision


def check_sms_channel(*, lead_state: LeadChannelState, trace_id: str) -> PolicyDecision:
    decision = can_use_sms(lead_state=lead_state, trace_id=trace_id)
    log_policy_decision(
        trace_id=trace_id,
        lead_id=lead_state.lead_id if hasattr(lead_state, "lead_id") else None,
        policy_input={"policy_type": "channel_policy"},
        policy_output=decision.model_dump(mode="json"),
        status="blocked" if not decision.is_allowed else "success",
    )
    return decision


def check_bench_commitment(
    *,
    service: OutboundPolicyService,
    trace_id: str,
    lead_id: str,
    message: str,
    bench_verified: bool,
) -> PolicyDecision:
    decision = service.check_bench_commitment(
        trace_id=trace_id,
        lead_id=lead_id,
        message=message,
        bench_verified=bench_verified,
    )
    log_policy_decision(
        trace_id=trace_id,
        lead_id=lead_id,
        policy_input={"policy_type": "bench_commitment"},
        policy_output=decision.model_dump(mode="json"),
        status="blocked" if not decision.is_allowed else "success",
    )
    return decision


def require_human_handoff(
    *,
    service: OutboundPolicyService,
    trace_id: str,
    lead_id: str,
    reason: str,
) -> PolicyDecision:
    decision = service.check_escalation_trigger(
        trace_id=trace_id,
        lead_id=lead_id,
        needs_human_handoff=True,
        reason=reason,
    )
    log_policy_decision(
        trace_id=trace_id,
        lead_id=lead_id,
        policy_input={"policy_type": "escalation"},
        policy_output=decision.model_dump(mode="json"),
        status="failure" if decision.decision == "escalate" else "success",
    )
    return decision
