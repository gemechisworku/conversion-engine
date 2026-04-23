"""mean_success (successful tasks / task×trial slots) + per-try pass@n for score_log."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from harness.metrics import mean_bootstrap_ci


def _trial_map(
    task_ids_per_sim: list[str],
    trial_indices: list[int],
    successes: list[float],
) -> dict[str, dict[int, float]]:
    m: dict[str, dict[int, float]] = defaultdict(dict)
    for tid, trial, succ in zip(task_ids_per_sim, trial_indices, successes, strict=True):
        m[tid][int(trial)] = float(succ)
    return dict(m)


def _task_passed_any_trial(trials: dict[int, float]) -> float:
    """1 if the task passed on at least one trial (reward>=1), else 0."""
    if not trials:
        return 0.0
    return 1.0 if max(trials.values()) >= 1.0 else 0.0


def _task_pass_on_trial(trials: dict[int, float], trial_idx: int) -> float:
    """Binary: did this task succeed on the given 0-based trial index?"""
    if trial_idx not in trials:
        return 0.0
    return float(trials[trial_idx])


def _bootstrap_mean_success_ci(
    task_any: np.ndarray,
    *,
    num_trials: int,
    seed: int,
    n_bootstrap: int,
) -> tuple[float, float, float]:
    """
    mean_success = task_any.sum() / (n_tasks * num_trials); bootstrap by resampling tasks.
    """
    n_tasks = int(task_any.size)
    denom = n_tasks * max(1, num_trials)
    if n_tasks == 0 or denom == 0:
        return 0.0, 0.0, 0.0
    mean = float(task_any.sum() / denom)
    if n_tasks == 1:
        return mean, mean, mean
    rng = np.random.default_rng(seed)
    stats = np.empty(n_bootstrap, dtype=np.float64)
    for b in range(n_bootstrap):
        idx = rng.integers(0, n_tasks, size=n_tasks)
        stats[b] = float(task_any[idx].sum() / denom)
    return mean, float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def build_experiment_metrics(
    *,
    task_ids_order: list[str],
    task_ids_per_sim: list[str],
    trial_indices: list[int],
    successes: list[float],
    num_trials: int,
    bootstrap_seed: int,
    bootstrap_B: int,
) -> dict[str, Any]:
    """
    - ``mean_success`` / ``ci95`` — (number of **successful tasks**, i.e. pass on ≥1 trial) /
      (``n_tasks`` × ``num_trials``); ``ci95`` bootstraps **tasks** (resample tasks, same ratio).
    - ``pass@1`` … ``pass@N`` — percentage (0–100) of tasks that pass **on try n only**;
      ``ci95_pass@n`` bootstraps **tasks** (per-try binary vector).
    """
    trial_map = _trial_map(task_ids_per_sim, trial_indices, successes)

    task_any = np.array(
        [_task_passed_any_trial(trial_map.get(tid, {})) for tid in task_ids_order],
        dtype=np.float64,
    )
    mean_ms, lo_ms, hi_ms = _bootstrap_mean_success_ci(
        task_any,
        num_trials=num_trials,
        seed=bootstrap_seed,
        n_bootstrap=bootstrap_B,
    )

    out: dict[str, Any] = {
        "mean_success": float(mean_ms),
        "ci95": {
            "low": lo_ms,
            "high": hi_ms,
            "method": "bootstrap_tasks",
            "bootstrap_B": bootstrap_B,
            "bootstrap_seed": bootstrap_seed,
        },
        "metrics_definitions": {
            "mean_success": (
                "mean_success = (number of successful tasks) / (n_tasks × num_trials_per_task). "
                "A task counts as successful if it achieves reward>=1 on at least one trial. "
                "Value in [0, 1]. ci95 bootstraps tasks with replacement (same formula per replicate)."
            ),
            "pass@n": (
                "For n=1,2,…, pass@n is the percentage (0–100) of tasks that achieve reward>=1 "
                "on the n-th attempt only (trial_index n-1). One entry per n up to "
                "num_trials_per_task. ci95_pass@n bootstraps tasks with replacement; "
                "low/high are also percentages."
            ),
        },
    }

    for t0 in range(num_trials):
        vec = [_task_pass_on_trial(trial_map.get(tid, {}), t0) for tid in task_ids_order]
        arr = np.array(vec, dtype=np.float64)
        mean_n, lo_n, hi_n = mean_bootstrap_ci(
            arr, seed=bootstrap_seed, n_bootstrap=bootstrap_B
        )
        n1 = t0 + 1
        pk = f"pass@{n1}"
        ck = f"ci95_pass@{n1}"
        out[pk] = float(mean_n * 100.0)
        out[ck] = {
            "low": float(lo_n * 100.0),
            "high": float(hi_n * 100.0),
            "method": "bootstrap_tasks",
            "bootstrap_B": bootstrap_B,
            "bootstrap_seed": bootstrap_seed,
        }

    return out
