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
