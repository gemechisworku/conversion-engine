from __future__ import annotations

from agent.services.orchestration.outreach_pipeline import (
    build_first_touch_outreach_request,
    _snippet_from_stored_briefs,
)


def test_snippet_prefers_hiring_segment() -> None:
    briefs = {"hiring_signal_brief": {"primary_segment_hypothesis": "  growth marketing  "}}
    assert _snippet_from_stored_briefs(briefs) == "growth marketing"


def test_snippet_falls_back_to_gap_angle() -> None:
    briefs = {"competitor_gap_brief": {"headline_angle": "Differentiation on compliance"}}
    assert _snippet_from_stored_briefs(briefs) == "Differentiation on compliance"


def test_build_first_touch_request_shape() -> None:
    req = build_first_touch_outreach_request(
        lead_id="lead_abc",
        to_email="a@b.com",
        company_name="Acme",
        trace_id="trace_1",
        idempotency_key="idem_1",
        briefs={"hiring_signal_brief": {"primary_segment_hypothesis": "SMB"}},
    )
    assert req.lead_id == "lead_abc"
    assert req.to_email == "a@b.com"
    assert "Acme" in req.subject
    assert "SMB" in (req.text_body or "")
    assert req.review_status == "approved"
    assert req.metadata.get("bench_verified") is True
