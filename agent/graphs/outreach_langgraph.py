"""LangGraph: outreach draft only (spec: draft is separate from review/send; outreach_api.md)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agent.config.settings import Settings
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.outreach.outreach_flow import OutreachFlowDeps, run_outreach_draft_only
from agent.services.policy.outbound_policy import OutboundPolicyService


class OutreachGraphState(TypedDict, total=False):
    lead_id: str
    trace_id: str
    idempotency_key: str
    to_email: str
    company_name: str
    prospect_first_name: str | None
    variant: str
    brief_id: str | None
    gap_brief_id: str | None
    errors: list[str]


@dataclass
class OutreachGraphDeps:
    settings: Settings
    llm: OpenRouterJSONClient | None
    state_repo: SQLiteStateRepository
    policy: OutboundPolicyService


def compile_outreach_draft_only_graph(deps: OutreachGraphDeps):
    """Single-step draft graph; review/send use REST /outreach/review and /outreach/send or runtime hooks."""
    graph: StateGraph = StateGraph(OutreachGraphState)
    flow = OutreachFlowDeps(
        settings=deps.settings,
        state_repo=deps.state_repo,
        llm=deps.llm,
        policy=deps.policy,
    )

    async def draft_only(state: OutreachGraphState) -> dict[str, Any]:
        try:
            await run_outreach_draft_only(
                flow,
                lead_id=state["lead_id"],
                trace_id=state["trace_id"],
                idempotency_key=state["idempotency_key"],
                to_email=state["to_email"],
                company_name=state["company_name"],
                variant=state.get("variant") or "cold_email",
                brief_id=state.get("brief_id"),
                gap_brief_id=state.get("gap_brief_id"),
                prospect_first_name=state.get("prospect_first_name"),
            )
        except Exception as exc:
            return {"errors": [str(exc)]}
        return {}

    graph.add_node("draft_only", draft_only)
    graph.set_entry_point("draft_only")
    graph.add_edge("draft_only", END)
    return graph.compile()


# Back-compat alias used by older imports
def compile_outreach_draft_review_graph(deps: OutreachGraphDeps):
    return compile_outreach_draft_only_graph(deps)
