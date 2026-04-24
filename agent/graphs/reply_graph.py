"""Reply handling orchestration entry (sync path for nodes; runtime uses reply_langgraph)."""

from __future__ import annotations

from agent.graphs.reply_routing import (
    classify_intent_from_text,
    next_action_for_intent,
    session_stage_for_next_action,
)
from agent.graphs.state import ReplyGraphState
from agent.graphs.transitions import validate_lead_transition
from agent.services.email.schemas import InboundEmailEvent
from agent.services.sms.schemas import InboundSMSEvent


def _inbound_text(inbound_event: InboundEmailEvent | InboundSMSEvent) -> str:
    if isinstance(inbound_event, InboundEmailEvent):
        return (inbound_event.text_body or inbound_event.html_body or "") or ""
    return (inbound_event.text or "") or ""


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
    intent = state.last_customer_intent
    if inbound_event.event_type in {"reply", "inbound_sms"}:
        text = _inbound_text(inbound_event)
        intent = classify_intent_from_text(text)
        next_action = next_action_for_intent(intent)
        next_session = session_stage_for_next_action(next_action)
        pending.append(
            {
                "action_type": "classify_intent",
                "status": "done",
                "intent": intent,
                "next_action": next_action,
                "next_session_stage_hint": next_session,
            }
        )
    return state.model_copy(
        update={
            "current_stage": next_stage,
            "pending_actions": pending,
            "last_customer_intent": intent,
        }
    )
