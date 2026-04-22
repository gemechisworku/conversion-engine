"""Aggregate metrics: bootstrap CI, percentiles."""

from __future__ import annotations

import numpy as np


def mean_bootstrap_ci(
    values: np.ndarray,
    *,
    seed: int,
    n_bootstrap: int = 5000,
) -> tuple[float, float, float]:
    """
    Bootstrap 95% CI for the mean of binary (or bounded) per-row values.

    Returns (mean, ci_low, ci_high).
    """
    if values.size == 0:
        return 0.0, 0.0, 0.0
    mean = float(values.mean())
    if values.size == 1:
        return mean, mean, mean
    rng = np.random.default_rng(seed)
    stats = np.empty(n_bootstrap, dtype=np.float64)
    n = values.size
    for b in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        stats[b] = float(values[idx].mean())
    return mean, float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def percentile_positive(xs: list[float], q: float) -> float:
    arr = np.array([x for x in xs if x is not None and x >= 0], dtype=np.float64)
    if arr.size == 0:
        return 0.0
    return float(np.percentile(arr, q))
