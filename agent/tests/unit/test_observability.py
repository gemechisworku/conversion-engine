from __future__ import annotations

import logging

from agent.services.observability.events import log_trace_event


def test_log_trace_event_emits_structured_record(caplog) -> None:
    caplog.set_level(logging.INFO, logger="agent.observability")

    log_trace_event(
        event_type="tool_call_succeeded",
        trace_id="trace_obs_1",
        lead_id="lead_obs_1",
        status="success",
        payload={"tool": "send_email"},
    )

    messages = [record.message for record in caplog.records]
    assert any("trace_event type=tool_call_succeeded" in message for message in messages)
    assert any("trace_id=trace_obs_1" in message for message in messages)

