"""Resume interrupted runs using flat ``trace_log_summary.jsonl`` lines."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# (success 0/1, cost_usd, wall_time_seconds)
Outcome = tuple[float, float, float]


def load_outcomes_from_trace_summary(
    path: Path,
    *,
    experiment_id: str,
    slice_name: str,
    domain: str,
    eval_run_index: int,
) -> dict[tuple[str, int], Outcome]:
    """
    Scan JSONL; last line wins per (task_id, trial_index).

    Only rows with ``eval_run_index`` equal to the given value are considered (so older
    evaluation commands with the same ``experiment_id`` do not affect resume). Rows
    without ``eval_run_index`` are ignored.
    """
    if not path.is_file():
        return {}
    out: dict[tuple[str, int], Outcome] = {}
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row: Any = json.loads(line)
            except json.JSONDecodeError:
                _log.warning("resume: skip invalid JSON at %s line %s", path, lineno)
                continue
            if not isinstance(row, dict):
                continue
            if row.get("experiment_id") != experiment_id:
                continue
            if row.get("slice") != slice_name:
                continue
            if row.get("domain") != domain:
                continue
            try:
                eri = row.get("eval_run_index")
                if eri is None or int(eri) != int(eval_run_index):
                    continue
            except (TypeError, ValueError):
                continue
            tid = row.get("task_id")
            tri = row.get("trial_index")
            if tid is None or tri is None:
                continue
            try:
                key = (str(tid), int(tri))
            except (TypeError, ValueError):
                continue
            succ = 1.0 if row.get("success") else 0.0
            try:
                cost = float(row.get("cost_usd") or 0.0)
            except (TypeError, ValueError):
                cost = 0.0
            try:
                wall = float(row.get("wall_time_seconds") or 0.0)
            except (TypeError, ValueError):
                wall = 0.0
            out[key] = (succ, cost, wall)
    return out


def merged_outcomes_to_run_lists(
    *,
    task_ids_order: list[str],
    num_trials: int,
    merged: dict[tuple[str, int], Outcome],
) -> tuple[list[str], list[int], list[float], list[float], list[float]]:
    """Canonical trial-major order aligned with ``execute_experiment`` scheduling."""
    task_ids_per_sim: list[str] = []
    trial_indices: list[int] = []
    successes: list[float] = []
    costs: list[float] = []
    walls: list[float] = []
    for trial in range(num_trials):
        for tid in task_ids_order:
            key = (tid, trial)
            if key not in merged:
                continue
            succ, c, w = merged[key]
            task_ids_per_sim.append(tid)
            trial_indices.append(trial)
            successes.append(succ)
            costs.append(c)
            walls.append(w)
    return task_ids_per_sim, trial_indices, successes, costs, walls
