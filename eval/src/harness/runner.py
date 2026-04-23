"""Execute τ-bench simulations and write trace_log + score_log + Langfuse."""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from harness.config import BaselineSettings, load_task_id_list
from harness.eval_run_state import allocate_eval_run_index
from harness.constants import HARNESS_HELDOUT_RUN_ENV, HARNESS_HELDOUT_RUN_VALUE
from harness.git_meta import git_rev
from harness.langfuse_sink import LangfuseSink
from harness.metrics_rollups import build_experiment_metrics
from harness.metrics import percentile_positive
from harness.resume_state import (
    load_outcomes_from_trace_summary,
    merged_outcomes_to_run_lists,
)
from harness.score_log import append_experiment
from harness.trace_payload import build_trace_simulation_field
from harness.trace_summary import (
    build_trace_summary_record,
    instruction_preview_from_task,
    message_count_from_sim,
    reward_value,
    termination_reason_str,
)
from harness.trace_writer import TraceWriter

_log = logging.getLogger(__name__)

# ``wait`` timeout so the main thread can handle Ctrl+C while workers are blocked on I/O.
_EXECUTOR_WAIT_TIMEOUT_S = 2.0


def _effective_trace_policy(settings: BaselineSettings, slice_name: str) -> str:
    if slice_name != "heldout":
        return "full"
    return settings.heldout_trace_policy


def _metadata_only_sim_dump(sim_dump: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": sim_dump.get("id"),
        "reward_info": sim_dump.get("reward_info"),
        "termination_reason": sim_dump.get("termination_reason"),
        "agent_cost": sim_dump.get("agent_cost"),
        "user_cost": sim_dump.get("user_cost"),
    }


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
    task_ids_source: str,
    slice_name: str = "dev",
    bootstrap_seed: int = 42,
    bootstrap_B: int = 5000,
    resume: bool = False,
) -> None:
    """Run all task×trial simulations, append traces, Langfuse, and one score_log entry.

    With ``resume=True``, reads ``trace_log_summary.jsonl`` for the current ``eval_run_index``
    (same ``experiment_id`` / ``slice`` / ``domain``) and skips completed task×trial pairs;
    ``score_log`` merges disk + this session (requires ``trace_summary_log_enabled``).
    """
    from tau2.runner.helpers import get_tasks

    out_dir = settings.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / settings.eval_run_state_filename
    eval_run_index = allocate_eval_run_index(state_path, resume=resume)
    sys.stderr.write(
        f"harness: eval_run_index={eval_run_index} resume={resume} "
        f"(state {state_path.name})\n"
    )

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

    by_id = {t.id: t for t in tasks}
    tasks_ordered = [by_id[i] for i in task_ids]
    task_ids_order = list(task_ids)

    cfg_dict = _build_cfg_dict(settings)
    random.seed(settings.seed)
    trial_seeds = [random.randint(0, 1_000_000) for _ in range(num_trials)]

    work: list[tuple[Any, int, int]] = []
    for trial in range(num_trials):
        seed_t = trial_seeds[trial]
        for task in tasks_ordered:
            work.append((task, trial, seed_t))

    trace_path = settings.output_dir / settings.trace_log_filename
    score_path = settings.output_dir / settings.score_log_filename
    summary_path = settings.output_dir / settings.trace_summary_log_filename

    prior_outcomes: dict[tuple[str, int], tuple[float, float, float]] = {}
    if resume:
        if not settings.trace_summary_log_enabled:
            raise ValueError(
                "resume=True requires trace_summary_log_enabled so progress can be read "
                f"from {settings.trace_summary_log_filename!r}"
            )
        prior_outcomes = load_outcomes_from_trace_summary(
            summary_path,
            experiment_id=experiment_id,
            slice_name=slice_name,
            domain=settings.domain,
            eval_run_index=eval_run_index,
        )
        n_before = len(work)
        work = [w for w in work if (w[0].id, w[1]) not in prior_outcomes]
        skipped = n_before - len(work)
        if skipped:
            _log.info(
                "resume: skipping %s completed task×trial pairs "
                "(experiment_id=%s eval_run_index=%s)",
                skipped,
                experiment_id,
                eval_run_index,
            )
        if not work:
            _log.warning(
                "resume: no remaining simulations for eval_run_index=%s in %s",
                eval_run_index,
                summary_path.name,
            )

    trace_writer = TraceWriter(trace_path)
    trace_summary_writer: TraceWriter | None = None
    if settings.trace_summary_log_enabled:
        trace_summary_writer = TraceWriter(summary_path)
    lf = LangfuseSink(settings.langfuse)

    tau2_sha = git_rev(settings.tau2_root)

    def _git_root(start: Path) -> Path:
        for p in [start, *start.parents]:
            if (p / ".git").is_dir() or (p / ".git").is_file():
                return p
        return start

    harness_sha = git_rev(_git_root(Path(__file__).resolve()))

    trace_policy = _effective_trace_policy(settings, slice_name)
    session_outcomes: dict[tuple[str, int], tuple[float, float, float]] = {}

    max_workers = max(1, settings.max_concurrency)
    futures: dict[Future, tuple[Any, int]] = {}
    interrupted = False
    pool = ThreadPoolExecutor(max_workers=max_workers)
    try:
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
        while pending and not interrupted:
            try:
                done, pending = wait(
                    pending,
                    return_when=FIRST_COMPLETED,
                    timeout=_EXECUTOR_WAIT_TIMEOUT_S,
                )
            except KeyboardInterrupt:
                interrupted = True
                _log.warning(
                    "KeyboardInterrupt: cancelling work not yet started; "
                    "in-flight simulations may finish in the background. "
                    "Press Ctrl+C again or stop the process if it does not exit."
                )
                for f in pending:
                    f.cancel()
                break
            if not done:
                continue
            for fut in done:
                if interrupted:
                    break
                task, trial = futures[fut]
                try:
                    sim, wall_s = fut.result()
                except KeyboardInterrupt:
                    interrupted = True
                    for f in pending:
                        f.cancel()
                    break
                succ = 1.0 if _success_from_sim(sim) else 0.0
                session_outcomes[(task.id, trial)] = (succ, _cost_usd(sim), wall_s)

                sim_dump = sim.model_dump(mode="json")
                run_id = sim.id
                recorded_at = datetime.now(timezone.utc).isoformat()
                lf_id: Optional[str] = None

                if trace_policy != "none":
                    if trace_policy == "metadata_only":
                        sim_export = _metadata_only_sim_dump(sim_dump)
                        line: dict[str, Any] = {
                            "schema_version": "1.3.0",
                            "eval_run_index": eval_run_index,
                            "run_id": run_id,
                            "recorded_at": recorded_at,
                            "experiment_id": experiment_id,
                            "slice": slice_name,
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
                            "trace_redaction": "metadata_only",
                            "trace_simulation_payload": settings.trace_simulation_payload,
                            "trace_export_max_chars": settings.trace_export_max_chars,
                            "simulation": sim_export,
                        }
                    else:
                        sim_export = build_trace_simulation_field(
                            sim_dump,
                            mode=settings.trace_simulation_payload,
                            max_chars=settings.trace_export_max_chars,
                        )
                        line = {
                            "schema_version": "1.3.0",
                            "eval_run_index": eval_run_index,
                            "run_id": run_id,
                            "recorded_at": recorded_at,
                            "experiment_id": experiment_id,
                            "slice": slice_name,
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
                            "trace_simulation_payload": settings.trace_simulation_payload,
                            "trace_export_max_chars": settings.trace_export_max_chars,
                            "simulation": sim_export,
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
                                simulation_output=sim_export,
                            )
                            if lf_id:
                                line["langfuse_trace_id"] = lf_id
                        except Exception as exc:
                            _log.warning("Langfuse export failed for %s: %s", run_id, exc)
                            line["langfuse_error"] = str(exc)[:2000]
                    trace_writer.append(line)

                if trace_summary_writer is not None:
                    summary = build_trace_summary_record(
                        eval_run_index=eval_run_index,
                        experiment_id=experiment_id,
                        slice_name=slice_name,
                        domain=settings.domain,
                        task_id=task.id,
                        trial_index=trial,
                        run_id=run_id,
                        wall_time_seconds=wall_s,
                        cost_usd=_cost_usd(sim),
                        success=_success_from_sim(sim),
                        reward=reward_value(sim),
                        termination_reason=termination_reason_str(sim),
                        message_count=message_count_from_sim(sim),
                        instruction_preview=instruction_preview_from_task(
                            task, settings.trace_summary_max_instruction_chars
                        ),
                        agent_llm=settings.agent_llm,
                        user_llm=settings.user_llm,
                        tau2_bench_git_sha=tau2_sha,
                        harness_git_sha=harness_sha,
                        langfuse_trace_id=lf_id,
                        recorded_at=recorded_at,
                    )
                    trace_summary_writer.append(summary)
            if interrupted:
                break
    except KeyboardInterrupt:
        interrupted = True
        _log.warning("KeyboardInterrupt during experiment execution.")
    finally:
        pool.shutdown(wait=not interrupted, cancel_futures=interrupted)

    if interrupted:
        _log.warning("Interrupted: score_log not updated for this invocation.")
        raise SystemExit(130)

    merged_outcomes = {**prior_outcomes, **session_outcomes}
    task_ids_per_sim, trial_indices, successes, costs, walls = merged_outcomes_to_run_lists(
        task_ids_order=task_ids_order,
        num_trials=num_trials,
        merged=merged_outcomes,
    )

    metrics_block = build_experiment_metrics(
        task_ids_order=task_ids_order,
        task_ids_per_sim=task_ids_per_sim,
        trial_indices=trial_indices,
        successes=successes,
        num_trials=num_trials,
        bootstrap_seed=bootstrap_seed,
        bootstrap_B=bootstrap_B,
    )

    experiment: dict[str, Any] = {
        "id": experiment_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "domain": settings.domain,
        "slice": slice_name,
        "heldout_trace_policy": trace_policy if slice_name == "heldout" else None,
        "eval_run_index": eval_run_index,
        "resume": resume,
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
        "task_ids_source": task_ids_source,
        "n_tasks": len(task_ids),
        "num_trials_per_task": num_trials,
        "n_simulations": len(merged_outcomes),
        "success_definition": "reward_info.reward >= 1.0",
        **metrics_block,
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
    resume: bool = False,
) -> Optional[Path]:
    """
    ``mode``:
    - ``full`` / ``dev`` — dev_task_ids_path × settings.num_trials
    - ``smoke`` — first 3 task ids, 1 trial (small-scale repro)
    - ``both`` — dev then smoke (two score_log entries)
    - ``heldout_prepare`` — validate held-out id file + manifest (no simulations)
    - ``heldout_run`` — held-out ids × num_trials (requires ``HARNESS_HELDOUT_RUN=1``)
    """
    if mode == "heldout_prepare":
        from harness.heldout_prepare import run_heldout_prepare

        return run_heldout_prepare(settings)

    if mode == "heldout_run":
        if os.environ.get(HARNESS_HELDOUT_RUN_ENV) != HARNESS_HELDOUT_RUN_VALUE:
            raise ValueError(
                f"Refusing held-out execution: set {HARNESS_HELDOUT_RUN_ENV}={HARNESS_HELDOUT_RUN_VALUE!r} "
                "when course staff authorizes sealed scoring on this machine."
            )
        if settings.heldout_task_ids_path is None or not settings.heldout_task_ids_path.is_file():
            raise ValueError(
                "heldout_run requires heldout_task_ids_path in baseline.yaml pointing to an existing file."
            )
        held_ids = load_task_id_list(settings.heldout_task_ids_path)
        execute_experiment(
            settings,
            experiment_id=f"{settings.experiment_name}_heldout",
            task_ids=held_ids,
            num_trials=settings.num_trials,
            description="Held-out slice baseline (gated execution).",
            task_ids_source=str(settings.heldout_task_ids_path.resolve()),
            slice_name="heldout",
            resume=resume,
        )
        return None

    if mode not in ("full", "dev", "smoke", "both"):
        raise ValueError(f"Unsupported mode after dispatch: {mode!r}")

    task_ids = load_task_id_list(settings.dev_task_ids_path)
    if mode in ("full", "dev", "both"):
        execute_experiment(
            settings,
            experiment_id=f"{settings.experiment_name}_dev",
            task_ids=task_ids,
            num_trials=settings.num_trials,
            description="Dev slice baseline (pass@n per try; see metrics_definitions).",
            task_ids_source=str(settings.dev_task_ids_path.resolve()),
            slice_name="dev",
            resume=resume,
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
            task_ids_source=str(settings.dev_task_ids_path.resolve()),
            slice_name="smoke",
            resume=resume,
        )
    return None
