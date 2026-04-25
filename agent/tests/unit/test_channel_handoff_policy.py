from __future__ import annotations

from agent.services.policy.channel_handoff import append_scheduling_cta, decide_channel_handoff
from agent.services.policy.channel_policy import LeadChannelState


def test_channel_handoff_blocks_sms_for_cold_lead() -> None:
    decision = decide_channel_handoff(
        lead_id="lead_1",
        requested_channel="sms",
        lead_state=LeadChannelState(lead_id="lead_1"),
        trace_id="trace_1",
    )
    assert decision.allowed is False
    assert decision.resolved_channel == "email"


def test_channel_handoff_allows_sms_for_warm_lead() -> None:
    decision = decide_channel_handoff(
        lead_id="lead_1",
        requested_channel="sms",
        lead_state=LeadChannelState(lead_id="lead_1", has_prior_email_reply=True),
        trace_id="trace_2",
    )
    assert decision.allowed is True
    assert decision.resolved_channel == "sms"


def test_append_scheduling_cta_appends_once() -> None:
    text = append_scheduling_cta(
        content="Thanks for the note.",
        channel="email",
        scheduling_portal_url="https://cal.com/demo?lead_id=lead_1",
    )
    assert "https://cal.com/demo?lead_id=lead_1" in text
    text2 = append_scheduling_cta(
        content=text,
        channel="email",
        scheduling_portal_url="https://cal.com/demo?lead_id=lead_1",
    )
    assert text2.count("https://cal.com/demo?lead_id=lead_1") == 1
