from __future__ import annotations

from unittest.mock import MagicMock

from agent.services.email.schemas import OutboundEmailRequest
from agent.services.outreach.reviewer_tools import (
    aggregate_tool_failures,
    run_reviewer_tool_sequence,
)


def _outbound(**meta) -> OutboundEmailRequest:
    return OutboundEmailRequest(
        lead_id="l1",
        draft_id="d1",
        review_id="r1",
        trace_id="t1",
        idempotency_key="i1",
        to_email="a@b.co",
        subject="Hi",
        text_body="Hello",
        metadata=dict(meta),
    )


def test_validate_claims_fails_on_unsupported_claims() -> None:
    policy = MagicMock()
    policy.check_bench_commitment.return_value = MagicMock(decision="pass", reason="")
    results = run_reviewer_tool_sequence(
        policy=policy,
        outbound=_outbound(unsupported_claims=True, bench_verified=True),
        hiring_signal_brief={"brief_id": "b1"},
        competitor_gap_brief={},
        trace_id="t",
        lead_id="l1",
    )
    assert results[0].tool == "validate_claims"
    assert results[0].passed is False
    issues = aggregate_tool_failures(results)
    assert any("validate_claims" in i for i in issues)


def test_aggregate_tool_failures_empty_notes_uses_failed_suffix() -> None:
    from agent.services.outreach.reviewer_tools import ReviewerToolResult

    issues = aggregate_tool_failures([ReviewerToolResult(tool="x", passed=False, notes=[])])
    assert issues == ["x:failed"]
