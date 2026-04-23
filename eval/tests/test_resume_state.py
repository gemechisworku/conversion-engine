import json
from pathlib import Path

from harness.resume_state import (
    load_outcomes_from_trace_summary,
    merged_outcomes_to_run_lists,
)


def _row(**kwargs):
    base = {
        "schema_version": "1.1.0",
        "eval_run_index": 1,
        "experiment_id": "exp_dev",
        "slice": "dev",
        "domain": "retail",
        "success": True,
        "cost_usd": 0.01,
        "wall_time_seconds": 2.5,
    }
    base.update(kwargs)
    return json.dumps(base, ensure_ascii=False)


def test_load_outcomes_filters_and_last_wins(tmp_path: Path):
    p = tmp_path / "trace_log_summary.jsonl"
    p.write_text(
        _row(task_id="1", trial_index=0, success=False)
        + "\n"
        + _row(task_id="1", trial_index=0, success=True, cost_usd=0.02)
        + "\n"
        + _row(task_id="1", trial_index=0, success=True, experiment_id="other")
        + "\n"
        + _row(task_id="2", trial_index=1, success=True)
        + "\n",
        encoding="utf-8",
    )
    out = load_outcomes_from_trace_summary(
        p,
        experiment_id="exp_dev",
        slice_name="dev",
        domain="retail",
        eval_run_index=1,
    )
    assert out[("1", 0)] == (1.0, 0.02, 2.5)
    assert out[("2", 1)] == (1.0, 0.01, 2.5)
    assert len(out) == 2


def test_merged_outcomes_to_run_lists_order():
    merged = {
        ("b", 1): (0.0, 1.0, 1.0),
        ("a", 0): (1.0, 0.0, 0.0),
    }
    tid, tri, succ, cost, wall = merged_outcomes_to_run_lists(
        task_ids_order=["a", "b"],
        num_trials=2,
        merged=merged,
    )
    assert tid == ["a", "b"]
    assert tri == [0, 1]
    assert succ == [1.0, 0.0]
    assert cost == [0.0, 1.0]
    assert wall == [0.0, 1.0]


def test_load_outcomes_respects_eval_run_index(tmp_path: Path):
    p = tmp_path / "trace_log_summary.jsonl"
    p.write_text(
        _row(task_id="1", trial_index=0, eval_run_index=1)
        + "\n"
        + _row(task_id="1", trial_index=0, eval_run_index=2, success=False)
        + "\n",
        encoding="utf-8",
    )
    o1 = load_outcomes_from_trace_summary(
        p,
        experiment_id="exp_dev",
        slice_name="dev",
        domain="retail",
        eval_run_index=1,
    )
    assert o1[("1", 0)][0] == 1.0
    o2 = load_outcomes_from_trace_summary(
        p,
        experiment_id="exp_dev",
        slice_name="dev",
        domain="retail",
        eval_run_index=2,
    )
    assert o2[("1", 0)][0] == 0.0
