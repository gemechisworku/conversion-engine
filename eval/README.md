# Act I evaluation harness

Wraps **`tau2-bench`** to run retail (or other) baselines, append **`trace_log.jsonl`** (**one JSON line per task×trial run**), append **`trace_log_summary.jsonl`** (**flat** fields only — short lines for editor scanning; written **as soon as each** task×trial **finishes**, same as the full trace line), merge **`score_log.json`** (**`mean_success`**, **`pass@1` … `pass@N`**, bootstrap CIs, cost and wall-clock percentiles), and optionally send **Langfuse** traces (SDK v4). Trace and Langfuse share the **same** `simulation` payload (see **`trace_simulation_payload`**).

**Specification:** [`PLAN.md`](PLAN.md) · **Schemas:** [`schemas/`](schemas/)

## Resume after interrupt (`--resume`)

If a long dev or held-out run stops mid-way (crash, Ctrl+C, 429 storm), re-run with the **same** `experiment_name` in `baseline.yaml` and add **`--resume`**:

```bash
uv run harness run -c config/baseline.yaml --mode full --resume
```

Each **fresh** command allocates a monotonic **`eval_run_index`** (stored in **`harness_eval_run_state.json`** under `output_dir`, tunable via **`eval_run_state_filename`**). Every **`trace_log_summary.jsonl`** and **`trace_log.jsonl`** line for that invocation carries the same index. **`experiment_id`** (e.g. `{experiment_name}_dev`) can repeat across commands; resume only skips `(task_id, trial_index)` rows that match **`experiment_id` + `slice` + `domain` + `eval_run_index`**. A **resume** reuses the **previous** index (does not bump the counter). Stderr prints `harness: eval_run_index=…` at startup so you can confirm you attached to the right run.

**Ctrl+C:** the executor waits with a short timeout so the main thread can receive **KeyboardInterrupt**; pending work that has not started is cancelled, **`score_log`** is **not** written for that invocation, and the process exits with code **130**. Simulations **already running** in worker threads may continue briefly until the process exits; a second interrupt or killing the process is normal on Windows if something is stuck in native I/O.

**Older summaries** without `eval_run_index` are ignored for resume filtering (migrate by letting one full run append new lines, or delete/rename old summary fragments if needed). **`trace_summary_log_enabled`** must stay **true** (default) for resume.

## Setup

```bash
cd harness
uv sync
```

- Copy [`config/baseline.example.yaml`](config/baseline.example.yaml) to `config/baseline.yaml` and set **`agent_llm`** / **`user_llm`** (e.g. OpenRouter LiteLLM ids).
- Edit **`splits/dev_task_ids.json`** (30 ids) when you have the official curriculum list.
- API keys live in **`../tau2-bench/.env`** (loaded automatically). OpenRouter: `OPENROUTER_API_KEY`.

## OpenRouter-only (no OpenAI / Anthropic keys)

τ-bench uses **LiteLLM**. If `tau2-bench/.env` still has a **placeholder** `OPENAI_API_KEY=<your_key_here>`, LiteLLM may try the **OpenAI** endpoint for some calls and fail with **`OpenAIException - Incorrect API key`**, even when `baseline.yaml` uses **`openrouter/...`** models.

**Fix:** In `tau2-bench/.env` keep **`OPENROUTER_API_KEY`** and **remove or comment out** `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` unless you intentionally use those providers. Restart the shell after editing.

Cost lines may log *“This model isn't mapped yet”* for new OpenRouter slugs; rewards still work — costs may show as `0` until LiteLLM adds pricing.

## OpenRouter 429 / `:free` models

If you see **`429 Too Many Requests`** or **`temporarily rate-limited upstream`** (common on **`:free`** models):

1. Set **`max_concurrency: 1`** in `baseline.yaml` so you do not run several agent+user LLM pairs at once.
2. Prefer a **paid** route or **non-`:free`** model for stable baselines.
3. The harness **retries** each simulation on rate-limit errors with **exponential backoff** (tune with `openrouter_rate_limit_attempts`, `openrouter_rate_limit_backoff_base_seconds`, `openrouter_rate_limit_backoff_max_seconds` in YAML).

## Langfuse

1. In `config/baseline.yaml` set:

```yaml
langfuse:
  enabled: true
  host: https://cloud.langfuse.com   # optional; or your self-hosted URL
```

2. In the same `.env` (or environment) add:

- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_BASE_URL` (or `LANGFUSE_HOST`) if not using the default cloud host.

Each simulation becomes a **Langfuse trace** (root span + numeric score `tau2_success`). The span **`output`** is the **same** object as the **`simulation`** field on that run’s **`trace_log.jsonl`** line (default **`trace_simulation_payload: compact`** = JSON capped at **`trace_export_max_chars`**; set **`full`** for full `SimulationRun` JSON in both places—large files).

**Trace IDs:** Langfuse v4 requires **32-character hex** trace ids. The harness uses `create_trace_id(seed=<tau2 SimulationRun.id>)`, so traces are **deterministic** and metadata includes **`tau2_simulation_run_id`** (the original UUID) for correlation.

**If Langfuse fails:** each run still writes **`trace_log.jsonl`**; failed exports add **`langfuse_error`** on that line and log a warning.

**`OPENAI_API_KEY` errors during τ-bench (retail + `evaluation_type: all`):** Many retail tasks include **`NL_ASSERTION`** in `reward_basis`. After the dialog, τ-bench runs the **NL-assertions judge** in `tau2/evaluator/evaluator_nl_assertions.py`, which calls `generate(model=DEFAULT_LLM_NL_ASSERTIONS, …)`. That default is **`gpt-4.1-2025-04-14`** in `tau2/config.py` → LiteLLM uses the **OpenAI** route and **`OPENAI_API_KEY`**.

**Fix (OpenRouter-only):** In `baseline.yaml` set **`nl_assertions_llm`** (and optional **`nl_assertions_llm_args`**) to the same OpenRouter model you use for the agent, or a small cheap slug. The harness patches both **`tau2.config`** and **`tau2.evaluator.evaluator_nl_assertions`** (the latter is required because that module imported the default model name at load time).

**Alternative:** `evaluation_type: all_ignore_basis` — skips the NL LLM judge entirely (ENV + ACTION + COMMUNICATE only). Scores **will not** match runs that include NL in the product.

**Other OpenAI defaults in τ-bench** (not used in a typical text retail harness run unless you enable features): `DEFAULT_LLM_ENV_INTERFACE`, `DEFAULT_LLM_EVAL_USER_SIMULATOR` (reviews), voice stacks, etc. — see `tau2/config.py`.

**`score_log.json` missing:** `score_log.json` is written **once at the end** of each `execute_experiment` call (`append_experiment`). If **any** simulation throws (e.g. NL judge auth error), the batch aborts **before** that write. **`--mode smoke`** still writes `score_log.json` when all smoke sims finish successfully; it is not skipped by smoke mode. **`trace_log.jsonl`** and **`trace_log_summary.jsonl`** are appended **per completed run** (inside the executor completion loop), so partial lines can appear from tasks that finished before a later failure. Disable the summary file with **`trace_summary_log_enabled: false`** in `baseline.yaml` if you do not want it.

## Metrics (`score_log.json`)

Each experiment includes:

- **`mean_success`** + **`ci95`** — **(number of successful tasks) ÷ (n_tasks × trials)** in **[0, 1]**: a task counts as successful if **`reward >= 1` on any trial**; denominator is still **task × trial slots**. CI bootstraps **tasks** (same ratio on resampled tasks). Differs from counting raw simulation wins when some tasks hit multiple successes.
- **`pass@1`**, **`pass@2`**, … **`pass@N`** (with `N = num_trials_per_task`) — for try **n** (1-based), the **percentage (0–100)** of tasks that pass **on that attempt only** (`trial_index == n-1`).
- **`ci95_pass@1`**, **`ci95_pass@2`**, … — bootstrap **95% CI over tasks** for each **`pass@n`** (`low` / `high` are also **0–100**).

Exact wording is duplicated under **`metrics_definitions`** in each experiment record.

## Held-out slice

1. Add **`heldout_task_ids_path`** (and optionally **`heldout_trace_policy`**: `full` \| `metadata_only` \| `none`) to `baseline.yaml`. Example list: `splits/heldout_task_ids.example.json` (20 ids, disjoint from the stock dev example list).
2. **`uv run harness run -c config/baseline.yaml --mode heldout_prepare`** — checks count (default **20**, tunable via **`expected_heldout_count`**), duplicates, disjointness vs dev, and writes **`outputs/heldout_prepare_manifest.json`** (sha256 of the id file). No API keys or simulations required. **`heldout_prepare` skips the Langfuse key check** even when Langfuse is enabled.
3. **`HARNESS_HELDOUT_RUN=1`** must be set in the environment before **`--mode heldout_run`** will execute simulations on the held-out ids (intentional gate). With **`heldout_trace_policy: none`**, nothing is appended to **`trace_log.jsonl`** for those runs (scores still go to **`score_log.json`**). **`metadata_only`** keeps a slim `simulation` object (reward, costs, ids) for local audit without full trajectories.

## Commands

```bash
# Health check (paths, keys, one-task load; optional dev vs held-out overlap)
uv run harness doctor -c config/baseline.yaml

# Dev slice × num_trials (from baseline.yaml); alias: --mode dev
uv run harness run -c config/baseline.yaml --mode full

# Small-scale repro only (first 3 task ids, 1 trial)
uv run harness run -c config/baseline.yaml --mode smoke

# Act I deliverable: dev then smoke (two score_log entries)
uv run harness run -c config/baseline.yaml --mode both

# Validate held-out id file + write manifest (no τ-bench runs)
uv run harness run -c config/baseline.yaml --mode heldout_prepare

# Held-out slice × num_trials (requires HARNESS_HELDOUT_RUN=1, e.g. in PowerShell: $env:HARNESS_HELDOUT_RUN='1')
uv run harness run -c config/baseline.yaml --mode heldout_run
```

### Tests (harness)

```bash
cd harness
uv sync --extra dev
uv run pytest tests -v
```

Artifacts default to **`../../outputs/`** from `harness/config/` → repo-root **`outputs/`** (`trace_log.jsonl`, `score_log.json`).

### `trace_log.jsonl` (one line per run)

- **One JSON object per line** per completed **task × trial** simulation (append-only).
- Top-level fields include **`experiment_id`**, **`task_id`**, **`trial_index`**, **`run_id`**, **`models`**, **`wall_time_seconds`**, **`trace_simulation_payload`**, and **`simulation`** (the payload mirrored to Langfuse).
- **`trace_simulation_payload`**: **`compact`** (default) truncates oversized `simulation` JSON with **`trace_export_max_chars`**; **`full`** writes the full run. Held-out **`metadata_only`** / **`none`** policies still apply to what is stored.

## Mock wiring smoke (optional)

```bash
uv run harness doctor -c config/smoke_mock.yaml
uv run harness run -c config/smoke_mock.yaml --mode full
```

Uses the **`mock`** domain and one task id (`create_task_1`); still calls the agent LLM unless you switch agent implementation.
