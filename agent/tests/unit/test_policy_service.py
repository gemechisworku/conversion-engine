from __future__ import annotations

from agent.config.settings import Settings
from agent.services.policy.outbound_policy import OutboundPolicyService


def _service() -> OutboundPolicyService:
    settings = Settings(challenge_mode=False, sink_routing_enabled=True, kill_switch_enabled=False)
    return OutboundPolicyService(settings)


def test_review_approval_blocks_pending_status() -> None:
    service = _service()
    decision = service.check_review_approval(
        trace_id="trace_1",
        lead_id="lead_1",
        review_id="review_1",
        review_status="pending",
    )
    assert decision.decision == "blocked"


def test_bench_commitment_blocks_unverified_commitment_language() -> None:
    service = _service()
    decision = service.check_bench_commitment(
        trace_id="trace_2",
        lead_id="lead_2",
        message="We have the exact team available right now for your stack.",
        bench_verified=False,
    )
    assert decision.decision == "blocked"


def test_claim_grounding_blocks_unsupported_claims() -> None:
    service = _service()
    decision = service.check_claim_grounding(
        trace_id="trace_3",
        lead_id="lead_3",
        unsupported_claims=True,
    )
    assert decision.decision == "blocked"

