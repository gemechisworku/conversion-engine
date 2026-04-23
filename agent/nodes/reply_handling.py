"""Reply handling node."""

from __future__ import annotations

from agent.graphs.reply_graph import run_reply_handling
from agent.graphs.state import ReplyGraphState
from agent.services.email.schemas import InboundEmailEvent
from agent.services.sms.schemas import InboundSMSEvent


def reply_handling_node(
    *,
    state: ReplyGraphState,
    inbound_event: InboundEmailEvent | InboundSMSEvent,
) -> ReplyGraphState:
    return run_reply_handling(state=state, inbound_event=inbound_event)

