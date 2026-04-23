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

