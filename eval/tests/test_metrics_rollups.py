"""Unit tests for mean_success (successful tasks / slots) vs pass@n."""

from __future__ import annotations

import numpy as np

from harness.metrics_rollups import build_experiment_metrics


def test_two_tasks_three_trials() -> None:
    """Both tasks eventually pass at least once → 2 successful tasks / 6 slots."""
    task_ids_order = ["a", "b"]
    task_ids_per_sim = ["a", "b", "a", "b", "a", "b"]
    trial_indices = [0, 0, 1, 1, 2, 2]
    successes = [0.0, 1.0, 0.0, 0.0, 1.0, 0.0]
    m = build_experiment_metrics(
        task_ids_order=task_ids_order,
        task_ids_per_sim=task_ids_per_sim,
        trial_indices=trial_indices,
        successes=successes,
        num_trials=3,
        bootstrap_seed=0,
        bootstrap_B=200,
    )
    assert m["mean_success"] == 2.0 / 6.0
    assert m["ci95"]["method"] == "bootstrap_tasks"
    assert m["pass@1"] == 50.0
    assert m["pass@2"] == 0.0
    assert m["pass@3"] == 50.0


def test_mean_success_vs_pooled_simulation_rate() -> None:
    """One task passes both trials, other fails both: 1 successful task / 4 slots = 0.25; pooled sims = 0.5."""
    task_ids_order = ["x", "y"]
    task_ids_per_sim = ["x", "x", "y", "y"]
    trial_indices = [0, 1, 0, 1]
    successes = [1.0, 1.0, 0.0, 0.0]
    m = build_experiment_metrics(
        task_ids_order=task_ids_order,
        task_ids_per_sim=task_ids_per_sim,
        trial_indices=trial_indices,
        successes=successes,
        num_trials=2,
        bootstrap_seed=42,
        bootstrap_B=500,
    )
    assert m["mean_success"] == 1.0 / 4.0
    pooled = sum(successes) / len(successes)
    assert pooled == 0.5
    assert m["pass@1"] == 50.0
    assert m["pass@2"] == 50.0


def test_pass_at_n_bootstrap_deterministic() -> None:
    task_ids_order = ["x", "y"]
    task_ids_per_sim = ["x", "x", "y", "y"]
    trial_indices = [0, 1, 0, 1]
    successes = [1.0, 0.0, 1.0, 1.0]
    a = build_experiment_metrics(
        task_ids_order=task_ids_order,
        task_ids_per_sim=task_ids_per_sim,
        trial_indices=trial_indices,
        successes=successes,
        num_trials=2,
        bootstrap_seed=123,
        bootstrap_B=1000,
    )
    b = build_experiment_metrics(
        task_ids_order=task_ids_order,
        task_ids_per_sim=task_ids_per_sim,
        trial_indices=trial_indices,
        successes=successes,
        num_trials=2,
        bootstrap_seed=123,
        bootstrap_B=1000,
    )
    assert a["mean_success"] == b["mean_success"] == 2.0 / 4.0
    assert a["pass@1"] == b["pass@1"]
    assert a["pass@1"] == 100.0
    assert a["pass@2"] == 50.0
    assert a["ci95_pass@1"]["low"] == b["ci95_pass@1"]["low"]
    assert np.isfinite(a["ci95_pass@2"]["high"])
