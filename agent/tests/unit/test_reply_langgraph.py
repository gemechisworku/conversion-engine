from __future__ import annotations

import asyncio
from uuid import uuid4

from agent.config.settings import Settings
from agent.graphs.reply_langgraph import ReplyRouteGraphDeps, compile_reply_route_graph
from agent.repositories.state_repo import SQLiteStateRepository


def test_reply_route_graph_schedule_intent() -> None:
    settings = Settings(
        challenge_mode=False,
        state_db_path=f"outputs/test_reply_graph_{uuid4().hex}.db",
        openrouter_api_key="",
    )
    repo = SQLiteStateRepository(db_path=settings.state_db_path)
    graph = compile_reply_route_graph(
        ReplyRouteGraphDeps(settings=settings, llm=None, state_repo=repo)
    )
    out = asyncio.run(
        graph.ainvoke(
            {
                "lead_id": "lead_x",
                "trace_id": "trace_r",
                "channel": "email",
                "content": "Can we book time next Tuesday afternoon?",
                "subject": "Re: intro",
                "company_name": "Acme",
                "hiring_signal_brief": {},
                "recent_outbound_snippet": None,
            }
        )
    )
    assert out["intent"] == "schedule"
    assert out["next_action"] == "schedule"
    assert out["next_state"] == "scheduling"
    assert out.get("reply_branch") == "schedule"
    assert any(p.get("branch") == "schedule" for p in out.get("branch_pending", []))
    assert out.get("routing_flags", {}).get("ratified") is False


def test_reply_route_graph_schedule_from_thread_not_latest_line() -> None:
    """Heuristic sees scheduling language in CONVERSATION_THREAD even if latest inbound is minimal."""
    settings = Settings(
        challenge_mode=False,
        state_db_path=f"outputs/test_reply_graph_{uuid4().hex}.db",
        openrouter_api_key="",
    )
    repo = SQLiteStateRepository(db_path=settings.state_db_path)
    graph = compile_reply_route_graph(
        ReplyRouteGraphDeps(settings=settings, llm=None, state_repo=repo)
    )
    out = asyncio.run(
        graph.ainvoke(
            {
                "lead_id": "lead_x",
                "trace_id": "trace_r2",
                "channel": "email",
                "content": "Sounds good — thanks.",
                "subject": "Re: intro",
                "company_name": "Acme",
                "hiring_signal_brief": {},
                "recent_outbound_snippet": None,
                "conversation_transcript": (
                    "[2026-04-25T12:00:00+00:00] outbound email:\n"
                    "Please tell me what day and time works for you.\n\n"
                    "---\n\n"
                    "[2026-04-25T16:40:00+00:00] inbound email:\n"
                    "Okay, tomorrow 4 PM EAT works for me."
                ),
            }
        )
    )
    assert out["intent"] == "schedule"
    assert out["next_action"] == "schedule"
    assert out.get("routing_flags", {}).get("ratified") is False


def test_reply_route_mixed_intent_ratifies_to_clarify_with_dual_playbook() -> None:
    settings = Settings(
        challenge_mode=False,
        state_db_path=f"outputs/test_reply_graph_{uuid4().hex}.db",
        openrouter_api_key="",
    )
    repo = SQLiteStateRepository(db_path=settings.state_db_path)
    graph = compile_reply_route_graph(
        ReplyRouteGraphDeps(settings=settings, llm=None, state_repo=repo)
    )
    out = asyncio.run(
        graph.ainvoke(
            {
                "lead_id": "lead_m",
                "trace_id": "trace_m",
                "channel": "email",
                "content": "That works for me. Can you explain whether onboarding is included?",
                "subject": "Re: intro",
                "company_name": "Acme",
                "hiring_signal_brief": {},
            }
        )
    )
    assert out["intent"] == "mixed_schedule_clarify"
    assert out["next_action"] == "clarify"
    assert out["next_state"] == "qualifying"
    pending = out.get("branch_pending") or []
    assert len(pending) == 2
    assert pending[0].get("action_type") == "answer_clarification"
    assert pending[1].get("action_type") == "delegate_scheduler"


def test_reply_route_underspecified_next_week_ratifies() -> None:
    settings = Settings(
        challenge_mode=False,
        state_db_path=f"outputs/test_reply_graph_{uuid4().hex}.db",
        openrouter_api_key="",
    )
    repo = SQLiteStateRepository(db_path=settings.state_db_path)
    graph = compile_reply_route_graph(
        ReplyRouteGraphDeps(settings=settings, llm=None, state_repo=repo)
    )
    out = asyncio.run(
        graph.ainvoke(
            {
                "lead_id": "lead_u",
                "trace_id": "trace_u",
                "channel": "email",
                "content": "Yes, let's do it next week.",
                "subject": "Re: intro",
                "company_name": "Acme",
                "hiring_signal_brief": {},
            }
        )
    )
    assert out["intent"] == "schedule_underspecified"
    assert out["next_action"] == "clarify"
    pending = out.get("branch_pending") or []
    assert any(p.get("action_type") == "clarify_scheduling_slot" for p in pending)
