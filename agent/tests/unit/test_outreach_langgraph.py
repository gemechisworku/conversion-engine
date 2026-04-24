from __future__ import annotations

import asyncio
from uuid import uuid4

from agent.config.settings import Settings
from agent.graphs.outreach_langgraph import OutreachGraphDeps, compile_outreach_draft_only_graph
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.policy.outbound_policy import OutboundPolicyService


def test_outreach_graph_persists_draft() -> None:
    db = f"outputs/test_outreach_graph_{uuid4().hex}.db"
    settings = Settings(
        challenge_mode=False,
        state_db_path=db,
        openrouter_api_key="",
    )
    repo = SQLiteStateRepository(db_path=db)
    policy = OutboundPolicyService(settings=settings)
    repo.upsert_briefs(
        lead_id="lead_test",
        hiring_signal_brief={"primary_segment_hypothesis": "saas"},
        competitor_gap_brief={"headline_angle": "hiring velocity"},
        ai_maturity_score={"score": 2},
    )
    graph = compile_outreach_draft_only_graph(
        OutreachGraphDeps(settings=settings, llm=None, state_repo=repo, policy=policy)
    )
    out = asyncio.run(
        graph.ainvoke(
            {
                "lead_id": "lead_test",
                "trace_id": "trace_t",
                "idempotency_key": "idem_o",
                "to_email": "p@example.com",
                "company_name": "Acme",
                "variant": "cold_email",
            }
        )
    )
    assert not out.get("errors")
    row = repo.get_outreach_draft(lead_id="lead_test")
    assert row is not None
    blob = row["draft"]
    outbound = blob.get("outbound", blob)
    assert outbound["subject"]
