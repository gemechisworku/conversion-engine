# Act I evaluation harness

Wraps **`tau2-bench`** to run retail (or other) baselines, append **`trace_log.jsonl`** (full `SimulationRun` JSON per line), merge **`score_log.json`** (mean success, bootstrap 95% CI, cost and wall-clock percentiles), and optionally send **Langfuse** traces (SDK v4).

**Specification:** [`PLAN.md`](PLAN.md) · **Schemas:** [`schemas/`](schemas/)

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

Each simulation becomes a **Langfuse trace** (root span + numeric score `tau2_success`) with **truncated** simulation JSON in the span output; the **canonical full trajectory** is always in **`trace_log.jsonl`**.

**Trace IDs:** Langfuse v4 requires **32-character hex** trace ids. The harness uses `create_trace_id(seed=<tau2 SimulationRun.id>)`, so traces are **deterministic** and metadata includes **`tau2_simulation_run_id`** (the original UUID) for correlation.

**If Langfuse fails:** each run still writes **`trace_log.jsonl`**; failed exports add **`langfuse_error`** on that line and log a warning.

**`OPENAI_API_KEY` errors during τ-bench (retail + `evaluation_type: all`):** Many retail tasks include **`NL_ASSERTION`** in `reward_basis`. After the dialog, τ-bench runs the **NL-assertions judge** in `tau2/evaluator/evaluator_nl_assertions.py`, which calls `generate(model=DEFAULT_LLM_NL_ASSERTIONS, …)`. That default is **`gpt-4.1-2025-04-14`** in `tau2/config.py` → LiteLLM uses the **OpenAI** route and **`OPENAI_API_KEY`**.

**Fix (OpenRouter-only):** In `baseline.yaml` set **`nl_assertions_llm`** (and optional **`nl_assertions_llm_args`**) to the same OpenRouter model you use for the agent, or a small cheap slug. The harness patches both **`tau2.config`** and **`tau2.evaluator.evaluator_nl_assertions`** (the latter is required because that module imported the default model name at load time).

**Alternative:** `evaluation_type: all_ignore_basis` — skips the NL LLM judge entirely (ENV + ACTION + COMMUNICATE only). Scores **will not** match runs that include NL in the product.

**Other OpenAI defaults in τ-bench** (not used in a typical text retail harness run unless you enable features): `DEFAULT_LLM_ENV_INTERFACE`, `DEFAULT_LLM_EVAL_USER_SIMULATOR` (reviews), voice stacks, etc. — see `tau2/config.py`.

**`score_log.json` missing:** `score_log.json` is written **once at the end** of each `execute_experiment` call (`append_experiment`). If **any** simulation throws (e.g. NL judge auth error), the batch aborts **before** that write. **`--mode smoke`** still writes `score_log.json` when all smoke sims finish successfully; it is not skipped by smoke mode. Partial `trace_log.jsonl` lines can appear from tasks that completed before the failure.

## Commands

```bash
# Health check (paths, keys, one-task load)
uv run harness doctor -c config/baseline.yaml

# Dev slice × num_trials (from baseline.yaml)
uv run harness run -c config/baseline.yaml --mode full

# Small-scale repro only (first 3 task ids, 1 trial)
uv run harness run -c config/baseline.yaml --mode smoke

# Act I deliverable: two score_log entries in one invocation
uv run harness run -c config/baseline.yaml --mode both
```

Artifacts default to **`../../outputs/`** from `harness/config/` → repo-root **`outputs/`** (`trace_log.jsonl`, `score_log.json`).

## Mock wiring smoke (optional)

```bash
uv run harness doctor -c config/smoke_mock.yaml
uv run harness run -c config/smoke_mock.yaml --mode full
```

Uses the **`mock`** domain and one task id (`create_task_1`); still calls the agent LLM unless you switch agent implementation.
