"""Flat one-line-per-run summary for JSONL scanning (separate from full trace_log.jsonl)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


SUMMARY_SCHEMA_VERSION = "1.1.0"


def _short_sha(sha: str) -> str:
    s = sha.strip()
    if len(s) <= 7:
        return s
    return s[:7]


def instruction_preview_from_task(task: Any, max_chars: int) -> str:
    """Single-line, whitespace-collapsed snippet of user scenario instructions."""
    instr = task.user_scenario.instructions
    text = str(instr)
    text = " ".join(text.split())
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def message_count_from_sim(sim: Any) -> int:
    try:
        msgs = sim.get_messages()
        return len(msgs) if msgs is not None else 0
    except Exception:
        return 0


def reward_value(sim: Any) -> Optional[float]:
    ri = getattr(sim, "reward_info", None)
    if ri is None:
        return None
    r = getattr(ri, "reward", None)
    if r is None:
        return None
    try:
        return float(r)
    except (TypeError, ValueError):
        return None


def termination_reason_str(sim: Any) -> str:
    tr = getattr(sim, "termination_reason", None)
    if tr is None:
        return ""
    if hasattr(tr, "value"):
        return str(tr.value)
    return str(tr)


def build_trace_summary_record(
    *,
    eval_run_index: int,
    experiment_id: str,
    slice_name: str,
    domain: str,
    task_id: str,
    trial_index: int,
    run_id: str,
    wall_time_seconds: float,
    cost_usd: float,
    success: bool,
    reward: Optional[float],
    termination_reason: str,
    message_count: int,
    instruction_preview: str,
    agent_llm: str,
    user_llm: str,
    tau2_bench_git_sha: str,
    harness_git_sha: str,
    langfuse_trace_id: Optional[str] = None,
    recorded_at: Optional[str] = None,
) -> dict[str, Any]:
    ts = recorded_at or datetime.now(timezone.utc).isoformat()
    row: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "eval_run_index": int(eval_run_index),
        "recorded_at": ts,
        "experiment_id": experiment_id,
        "slice": slice_name,
        "domain": domain,
        "task_id": task_id,
        "trial_index": trial_index,
        "run_id": run_id,
        "success": success,
        "reward": reward,
        "termination_reason": termination_reason,
        "wall_time_seconds": wall_time_seconds,
        "cost_usd": cost_usd,
        "message_count": message_count,
        "instruction_preview": instruction_preview,
        "agent_llm": agent_llm,
        "user_llm": user_llm,
        "tau2_bench_git_sha": _short_sha(tau2_bench_git_sha),
        "harness_git_sha": _short_sha(harness_git_sha),
    }
    if langfuse_trace_id:
        row["langfuse_trace_id"] = langfuse_trace_id
    return row
