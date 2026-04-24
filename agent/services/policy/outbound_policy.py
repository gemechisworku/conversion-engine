"""Policy checks for outbound channel actions."""

from __future__ import annotations

from agent.config.settings import Settings
from agent.services.common.schemas import PolicyDecision


class OutboundPolicyService:
    # Implements: FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: policy_decision.md
    # API: policy_api.md
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check_kill_switch(self, *, trace_id: str, lead_id: str) -> PolicyDecision:
        if self._settings.kill_switch_enabled:
            return PolicyDecision(
                policy_type="kill_switch",
                decision="blocked",
                reason="Global kill switch is enabled.",
                trace_id=trace_id,
                lead_id=lead_id,
            )
        return PolicyDecision(
            policy_type="kill_switch",
            decision="pass",
            reason="Kill switch is disabled.",
            trace_id=trace_id,
            lead_id=lead_id,
        )

    def check_sink_routing(self, *, trace_id: str, lead_id: str) -> PolicyDecision:
        if not self._settings.sink_routing_enabled and self._settings.challenge_mode:
            return PolicyDecision(
                policy_type="sink_routing",
                decision="blocked",
                reason="Sink routing is required in challenge mode.",
                trace_id=trace_id,
                lead_id=lead_id,
            )
        return PolicyDecision(
            policy_type="sink_routing",
            decision="pass",
            reason="Sink routing check passed.",
            trace_id=trace_id,
            lead_id=lead_id,
        )

    def check_email_send(self, *, trace_id: str, lead_id: str) -> list[PolicyDecision]:
        return [
            self.check_kill_switch(trace_id=trace_id, lead_id=lead_id),
            self.check_sink_routing(trace_id=trace_id, lead_id=lead_id),
        ]

    def check_review_approval(
        self,
        *,
        trace_id: str,
        lead_id: str,
        review_id: str,
        review_status: str,
    ) -> PolicyDecision:
        if not review_id.strip():
            return PolicyDecision(
                policy_type="claim_validation",
                decision="blocked",
                reason="Missing review_id; outbound send requires completed review.",
                trace_id=trace_id,
                lead_id=lead_id,
            )
        if review_status not in {"approved", "approved_with_edits"}:
            return PolicyDecision(
                policy_type="claim_validation",
                decision="blocked",
                reason=f"Review status '{review_status}' is not send-eligible.",
                trace_id=trace_id,
                lead_id=lead_id,
            )
        return PolicyDecision(
            policy_type="claim_validation",
            decision="pass",
            reason="Review approval check passed.",
            trace_id=trace_id,
            lead_id=lead_id,
        )

    def check_bench_commitment(
        self,
        *,
        trace_id: str,
        lead_id: str,
        message: str,
        bench_verified: bool,
    ) -> PolicyDecision:
        commitment_terms = ("exact team", "5-person", "can start next week", "guaranteed capacity")
        lowered = message.lower()
        if any(term in lowered for term in commitment_terms) and not bench_verified:
            return PolicyDecision(
                policy_type="bench_commitment",
                decision="blocked",
                reason="Bench commitment language detected without verification.",
                trace_id=trace_id,
                lead_id=lead_id,
            )
        return PolicyDecision(
            policy_type="bench_commitment",
            decision="pass",
            reason="Bench commitment check passed.",
            trace_id=trace_id,
            lead_id=lead_id,
        )

    def check_claim_grounding(
        self,
        *,
        trace_id: str,
        lead_id: str,
        unsupported_claims: bool,
    ) -> PolicyDecision:
        if unsupported_claims:
            return PolicyDecision(
                policy_type="claim_validation",
                decision="blocked",
                reason="Unsupported claims were flagged for this draft.",
                trace_id=trace_id,
                lead_id=lead_id,
            )
        return PolicyDecision(
            policy_type="claim_validation",
            decision="pass",
            reason="Claim grounding check passed.",
            trace_id=trace_id,
            lead_id=lead_id,
        )

    def check_escalation_trigger(
        self,
        *,
        trace_id: str,
        lead_id: str,
        needs_human_handoff: bool,
        reason: str = "",
    ) -> PolicyDecision:
        if needs_human_handoff:
            return PolicyDecision(
                policy_type="escalation",
                decision="escalate",
                reason=reason or "Human handoff required by policy trigger.",
                trace_id=trace_id,
                lead_id=lead_id,
            )
        return PolicyDecision(
            policy_type="escalation",
            decision="pass",
            reason="No escalation trigger detected.",
            trace_id=trace_id,
            lead_id=lead_id,
        )
