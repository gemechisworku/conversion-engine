"""Execute τ-bench simulations and write trace_log + score_log + Langfuse."""

from __future__ import annotations

import logging
import random
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from harness.config import BaselineSettings, load_task_id_list
from harness.git_meta import git_rev
from harness.langfuse_sink import LangfuseSink
from harness.metrics import mean_bootstrap_ci, percentile_positive
from harness.score_log import append_experiment
from harness.trace_writer import TraceWriter

_log = logging.getLogger(__name__)


def _evaluation_type(name: str):
    from tau2.evaluator.evaluator import EvaluationType

    return EvaluationType(name)


def _success_from_sim(sim) -> bool:
    if sim.reward_info is None or sim.reward_info.reward is None:
        return False
    return float(sim.reward_info.reward) >= 1.0


def _cost_usd(sim) -> float:
    a = sim.agent_cost if sim.agent_cost is not None else 0.0
    u = sim.user_cost if sim.user_cost is not None else 0.0
    return float(a) + float(u)


def _is_provider_rate_limit(exc: BaseException) -> bool:
    """429 / rate-limit from OpenRouter or LiteLLM-wrapped providers."""
    msg = str(exc).lower()
    if "429" in str(exc) or " 429 " in msg or "too many requests" in msg:
        return True
    if "rate" in msg and "limit" in msg:
        return True
    if "temporarily rate-limited" in msg:
        return True
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "rate_limit" in name:
        return True
    return False


def _run_single(
    cfg_template: dict[str, Any],
    task,
    *,
    _trial_index: int,
    seed: int,
    evaluation_type,
    rate_limit_attempts: int,
    rate_limit_backoff_base: float,
    rate_limit_backoff_max: float,
) -> tuple[object, float]:
    """Returns (simulation, wall_seconds). Imports tau2 inside worker thread."""
    from tau2.data_model.simulation import TextRunConfig
    from tau2.runner.batch import run_single_task

    text_cfg = TextRunConfig.model_validate(cfg_template)
    t0 = time.perf_counter()
    last_exc: BaseException | None = None
    for attempt in range(max(1, rate_limit_attempts)):
        try:
            sim = run_single_task(
                text_cfg,
                task,
                seed=seed,
                evaluation_type=evaluation_type,
                save_dir=None,
                auto_review=False,
            )
            wall = time.perf_counter() - t0
            return sim, wall
        except BaseException as e:
            last_exc = e
            if not _is_provider_rate_limit(e) or attempt >= rate_limit_attempts - 1:
                raise
            # Exponential backoff with cap (429 storms on :free tier).
            delay = min(
                rate_limit_backoff_max,
                rate_limit_backoff_base * (2**attempt),
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _apply_nl_assertions_override(settings: BaselineSettings) -> None:
    """Point τ-bench NL-assertion judge at OpenRouter (or any LiteLLM model) instead of default GPT.

    ``evaluator_nl_assertions`` does ``from tau2.config import DEFAULT_LLM_NL_ASSERTIONS``, which
    binds the **string at import time**. Updating ``tau2.config`` alone is not enough; we must
    also patch the name inside ``tau2.evaluator.evaluator_nl_assertions``.
    """
    if not settings.nl_assertions_llm:
        return
    import tau2.config as tc
    import tau2.evaluator.evaluator_nl_assertions as nlm

    merged = dict(tc.DEFAULT_LLM_NL_ASSERTIONS_ARGS)
    merged.update(settings.nl_assertions_llm_args or {})

    tc.DEFAULT_LLM_NL_ASSERTIONS = settings.nl_assertions_llm
    tc.DEFAULT_LLM_NL_ASSERTIONS_ARGS = merged
    nlm.DEFAULT_LLM_NL_ASSERTIONS = settings.nl_assertions_llm
    nlm.DEFAULT_LLM_NL_ASSERTIONS_ARGS = merged


def _build_cfg_dict(settings: BaselineSettings) -> dict[str, Any]:
    return {
        "domain": settings.domain,
        "task_set_name": None,
        "task_split_name": settings.task_split_name,
        "task_ids": None,
        "num_trials": 1,
        "num_tasks": None,
        "agent": settings.agent_implementation,
        "user": settings.user_implementation,
        "llm_agent": settings.agent_llm,
        "llm_user": settings.user_llm,
        "llm_args_agent": dict(settings.agent_llm_args or {}),
        "llm_args_user": dict(settings.user_llm_args or {}),
        "max_steps": settings.max_steps,
        "max_errors": settings.max_errors,
        "seed": settings.seed,
        "max_concurrency": 1,
        "log_level": settings.log_level,
        "auto_review": False,
        "max_retries": settings.max_retries,
        "retry_delay": settings.retry_delay,
        "save_to": None,
        "auto_resume": False,
        "hallucination_retries": 0,
    }


def execute_experiment(
    settings: BaselineSettings,
    *,
    experiment_id: str,
    task_ids: list[str],
    num_trials: int,
    description: str,
    bootstrap_seed: int = 42,
    bootstrap_B: int = 5000,
) -> None:
    """Run all task×trial simulations, append traces, Langfuse, and one score_log entry."""
    from tau2.runner.helpers import get_tasks

    _apply_nl_assertions_override(settings)
    eval_type = _evaluation_type(settings.evaluation_type)
    tasks = get_tasks(
        task_set_name=settings.domain,
        task_split_name=settings.task_split_name,
        task_ids=task_ids,
        num_tasks=None,
    )
    if len(tasks) != len(task_ids):
        missing = set(task_ids) - {t.id for t in tasks}
        raise ValueError(f"Missing tasks for domain {settings.domain}: {missing}")

    cfg_dict = _build_cfg_dict(settings)
    random.seed(settings.seed)
    trial_seeds = [random.randint(0, 1_000_000) for _ in range(num_trials)]

    work: list[tuple[Any, int, int]] = []
    for trial in range(num_trials):
        seed_t = trial_seeds[trial]
        for task in tasks:
            work.append((task, trial, seed_t))

    trace_path = settings.output_dir / settings.trace_log_filename
    score_path = settings.output_dir / settings.score_log_filename
    trace_writer = TraceWriter(trace_path)
    lf = LangfuseSink(settings.langfuse)

    tau2_sha = git_rev(settings.tau2_root)

    def _git_root(start: Path) -> Path:
        for p in [start, *start.parents]:
            if (p / ".git").is_dir() or (p / ".git").is_file():
                return p
        return start

    harness_sha = git_rev(_git_root(Path(__file__).resolve()))

    successes: list[float] = []
    costs: list[float] = []
    walls: list[float] = []

    max_workers = max(1, settings.max_concurrency)
    futures: dict[Future, tuple[Any, int]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for task, trial, seed_t in work:
            fut = pool.submit(
                _run_single,
                cfg_dict,
                task,
                _trial_index=trial,
                seed=seed_t,
                evaluation_type=eval_type,
                rate_limit_attempts=settings.openrouter_rate_limit_attempts,
                rate_limit_backoff_base=settings.openrouter_rate_limit_backoff_base_seconds,
                rate_limit_backoff_max=settings.openrouter_rate_limit_backoff_max_seconds,
            )
            futures[fut] = (task, trial)

        pending = set(futures.keys())
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                task, trial = futures[fut]
                sim, wall_s = fut.result()
                successes.append(1.0 if _success_from_sim(sim) else 0.0)
                costs.append(_cost_usd(sim))
                walls.append(wall_s)

                sim_dump = sim.model_dump(mode="json")
                run_id = sim.id
                line: dict[str, Any] = {
                    "schema_version": "1.0.0",
                    "run_id": run_id,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "experiment_id": experiment_id,
                    "domain": settings.domain,
                    "task_id": task.id,
                    "trial_index": trial,
                    "tau2_bench_git_sha": tau2_sha,
                    "harness_git_sha": harness_sha,
                    "models": {
                        "agent_llm": settings.agent_llm,
                        "user_llm": settings.user_llm,
                    },
                    "wall_time_seconds": wall_s,
                    "simulation": sim_dump,
                }
                if lf.enabled:
                    try:
                        lf_id = lf.log_simulation(
                            tau2_run_id=run_id,
                            domain=settings.domain,
                            task_id=task.id,
                            trial_index=trial,
                            experiment_name=experiment_id,
                            agent_llm=settings.agent_llm,
                            user_llm=settings.user_llm,
                            wall_time_s=wall_s,
                            sim_dump=sim_dump,
                        )
                        if lf_id:
                            line["langfuse_trace_id"] = lf_id
                    except Exception as exc:
                        _log.warning("Langfuse export failed for %s: %s", run_id, exc)
                        line["langfuse_error"] = str(exc)[:2000]
                trace_writer.append(line)

    arr = np.array(successes, dtype=np.float64)
    mean_s, lo, hi = mean_bootstrap_ci(arr, seed=bootstrap_seed, n_bootstrap=bootstrap_B)

    experiment: dict[str, Any] = {
        "id": experiment_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "domain": settings.domain,
        "tau2_bench_git_sha": tau2_sha,
        "harness_git_sha": harness_sha,
        "config": {
            "experiment_name": settings.experiment_name,
            "agent_llm": settings.agent_llm,
            "user_llm": settings.user_llm,
            "task_split_name": settings.task_split_name,
            "num_trials": num_trials,
            "max_concurrency": settings.max_concurrency,
            "evaluation_type": settings.evaluation_type,
        },
        "task_ids_source": str(settings.dev_task_ids_path),
        "n_tasks": len(task_ids),
        "num_trials_per_task": num_trials,
        "n_simulations": len(successes),
        "success_definition": "reward_info.reward >= 1.0",
        "mean_success": mean_s,
        "ci95": {
            "low": lo,
            "high": hi,
            "method": "bootstrap",
            "bootstrap_B": bootstrap_B,
            "bootstrap_seed": bootstrap_seed,
        },
        "cost_usd": {
            "definition": "agent_cost + user_cost from SimulationRun (0 if null)",
            "mean_per_simulation": float(np.mean(costs)) if costs else 0.0,
            "p50_per_simulation": percentile_positive(costs, 50),
            "p95_per_simulation": percentile_positive(costs, 95),
            "total": float(np.sum(costs)) if costs else 0.0,
        },
        "wall_time_seconds": {
            "p50_per_simulation": percentile_positive(walls, 50),
            "p95_per_simulation": percentile_positive(walls, 95),
            "total_batch": float(np.sum(walls)) if walls else 0.0,
        },
    }
    append_experiment(score_path, experiment)


def run_from_settings(
    settings: BaselineSettings,
    *,
    mode: str = "full",
) -> None:
    """
    ``mode``:
    - ``full`` — dev_task_ids_path × settings.num_trials
    - ``smoke`` — first 3 task ids, 1 trial (small-scale repro)
    - ``both`` — full then smoke (two score_log entries)
    """
    task_ids = load_task_id_list(settings.dev_task_ids_path)
    if mode in ("full", "both"):
        execute_experiment(
            settings,
            experiment_id=f"{settings.experiment_name}_dev",
            task_ids=task_ids,
            num_trials=settings.num_trials,
            description="Dev slice baseline (pass@1-style rollouts per task×trial).",
        )
    if mode in ("smoke", "both"):
        smoke_ids = task_ids[:3] if len(task_ids) >= 3 else task_ids
        if not smoke_ids:
            raise ValueError("No task ids for smoke repro.")
        execute_experiment(
            settings,
            experiment_id=f"{settings.experiment_name}_smoke_repro",
            task_ids=smoke_ids,
            num_trials=1,
            description="Small-scale reproduction check (≤3 tasks, 1 trial).",
        )
