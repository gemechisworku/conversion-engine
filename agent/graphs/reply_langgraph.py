"""LangGraph: inbound reply → intent → optional email LLM → routed session stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agent.config.settings import Settings
from agent.graphs.reply_routing import (
    classify_intent_from_text,
    next_action_for_intent,
    session_stage_for_next_action,
)
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.conversation.email_llm import interpret_inbound_email_and_draft_reply
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.observability.events import log_processing_step


class ReplyRouteGraphState(TypedDict, total=False):
    # Implements: FR-9
    # Workflow: reply_handling.md
    # API: orchestration_api.md
    lead_id: str
    trace_id: str
    channel: str
    content: str
    subject: str | None
    company_name: str
    hiring_signal_brief: dict[str, Any]
    recent_outbound_snippet: str | None
    conversation_transcript: str | None
    intent: str
    next_action: str
    next_state: str
    email_interp: dict[str, Any] | None
    reply_branch: str
    branch_pending: list[dict[str, Any]]


@dataclass
class ReplyRouteGraphDeps:
    settings: Settings
    llm: OpenRouterJSONClient | None
    state_repo: SQLiteStateRepository


def compile_reply_route_graph(deps: ReplyRouteGraphDeps):
    graph: StateGraph = StateGraph(ReplyRouteGraphState)

    async def classify_heuristic(state: ReplyRouteGraphState) -> dict[str, Any]:
        parts: list[str] = []
        transcript = (state.get("conversation_transcript") or "").strip()
        if transcript:
            parts.append(transcript)
        body = (state.get("content") or "").strip()
        if body:
            parts.append(body)
        combined = "\n\n".join(parts) if parts else ""
        intent = classify_intent_from_text(combined)
        next_action = next_action_for_intent(intent)
        log_processing_step(
            component="graphs.reply_route",
            step="classify.heuristic",
            message="Heuristic intent classification",
            lead_id=state.get("lead_id"),
            trace_id=state.get("trace_id"),
            intent=intent,
            next_action=next_action,
        )
        return {"intent": intent, "next_action": next_action}

    async def refine_email_llm(state: ReplyRouteGraphState) -> dict[str, Any]:
        if (state.get("channel") or "").lower() != "email":
            return {}
        llm = deps.llm
        if llm is None or not llm.configured:
            return {}
        hiring = state.get("hiring_signal_brief") or {}
        email_interp = await interpret_inbound_email_and_draft_reply(
            settings=deps.settings,
            llm=llm,
            company_name=state.get("company_name") or "",
            inbound_subject=state.get("subject") or "(no subject)",
            inbound_body=state.get("content") or "",
            recent_outbound_context=state.get("recent_outbound_snippet"),
            conversation_transcript=state.get("conversation_transcript"),
            hiring_signal_brief=hiring if isinstance(hiring, dict) else {},
            trace_id=state.get("trace_id"),
            lead_id=state.get("lead_id"),
        )
        if email_interp is None:
            return {}
        allowed_actions = {
            "schedule",
            "qualify",
            "clarify",
            "handle_objection",
            "nurture",
            "escalate",
        }
        next_action = email_interp.next_best_action
        if next_action not in allowed_actions:
            next_action = next_action_for_intent(email_interp.intent)
        log_processing_step(
            component="graphs.reply_route",
            step="classify.llm_email",
            message="LLM refined inbound email interpretation",
            lead_id=state.get("lead_id"),
            trace_id=state.get("trace_id"),
            intent=email_interp.intent,
            next_action=next_action,
        )
        return {
            "intent": email_interp.intent,
            "next_action": next_action,
            "email_interp": email_interp.model_dump(mode="json"),
        }

    def route_session_stage(state: ReplyRouteGraphState) -> dict[str, Any]:
        next_action = state.get("next_action") or "clarify"
        next_state = session_stage_for_next_action(next_action)
        return {"next_state": next_state}

    def emit_branch_playbook(state: ReplyRouteGraphState) -> dict[str, Any]:
        """reply_handling.md §7 — branch-specific next playbook (pending_actions)."""
        na = state.get("next_action") or "clarify"
        playbooks: dict[str, tuple[str, list[dict[str, Any]]]] = {
            "schedule": (
                "schedule",
                [{"action_type": "delegate_scheduler", "status": "pending", "branch": "schedule"}],
            ),
            "qualify": (
                "interest",
                [{"action_type": "continue_qualification", "status": "pending", "branch": "interest"}],
            ),
            "clarify": (
                "clarify",
                [{"action_type": "answer_clarification", "status": "pending", "branch": "clarify"}],
            ),
            "handle_objection": (
                "objection",
                [{"action_type": "handle_objection", "status": "pending", "branch": "objection"}],
            ),
            "nurture": ("decline", [{"action_type": "nurture", "status": "pending", "branch": "decline"}]),
            "escalate": (
                "escalate",
                [{"action_type": "escalate", "status": "pending", "branch": "escalate"}],
            ),
        }
        branch, pending = playbooks.get(na, playbooks["clarify"])
        log_processing_step(
            component="graphs.reply_route",
            step="branch.playbook",
            message="Reply branch playbook selected",
            lead_id=state.get("lead_id"),
            trace_id=state.get("trace_id"),
            reply_branch=branch,
            next_action=na,
        )
        return {"reply_branch": branch, "branch_pending": pending}

    graph.add_node("classify_heuristic", classify_heuristic)
    graph.add_node("refine_email_llm", refine_email_llm)
    graph.add_node("route_session_stage", route_session_stage)
    graph.add_node("emit_branch_playbook", emit_branch_playbook)
    graph.set_entry_point("classify_heuristic")
    graph.add_edge("classify_heuristic", "refine_email_llm")
    graph.add_edge("refine_email_llm", "route_session_stage")
    graph.add_edge("route_session_stage", "emit_branch_playbook")
    graph.add_edge("emit_branch_playbook", END)
    return graph.compile()
