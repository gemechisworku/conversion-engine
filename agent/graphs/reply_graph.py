"""Reply handling orchestration entry."""

from __future__ import annotations

from agent.graphs.state import ReplyGraphState
from agent.graphs.transitions import validate_lead_transition
from agent.services.email.schemas import InboundEmailEvent
from agent.services.sms.schemas import InboundSMSEvent


def run_reply_handling(
    *,
    state: ReplyGraphState,
    inbound_event: InboundEmailEvent | InboundSMSEvent,
) -> ReplyGraphState:
    # Implements: FR-9
    # Workflow: reply_handling.md
    # Schema: conversation_state.md
    # API: orchestration_api.md
    validate_lead_transition(from_state=state.current_stage, to_state="reply_received")
    next_stage = "reply_received"
    pending = list(state.pending_actions)
    if inbound_event.event_type in {"reply", "inbound_sms"}:
        pending.append({"action_type": "classify_intent", "status": "pending"})
    return state.model_copy(update={"current_stage": next_stage, "pending_actions": pending})
