from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from agent.repositories.state_repo import SQLiteStateRepository


def test_append_and_list_evidence_edges() -> None:
    db = Path(f"outputs/test_evidence_{uuid4().hex}.db")
    repo = SQLiteStateRepository(db_path=str(db))
    lead = "lead_ev_1"
    repo.upsert_session_state(
        lead_id=lead,
        payload={
            "current_stage": "new_lead",
            "next_best_action": "enrich",
            "current_objective": "x",
            "brief_refs": [],
            "kb_refs": [],
            "pending_actions": [],
            "policy_flags": [],
            "handoff_required": False,
        },
    )
    repo.append_evidence_edge(
        lead_id=lead,
        trace_id="trace_1",
        edge_type="brief.hiring_signal",
        brief_id="brief_a",
        payload={"k": 1},
    )
    rows = repo.list_evidence_edges(lead_id=lead)
    assert len(rows) == 1
    assert rows[0]["edge_type"] == "brief.hiring_signal"
    assert rows[0]["brief_id"] == "brief_a"
    assert rows[0]["payload"] == {"k": 1}
    db.unlink(missing_ok=True)
