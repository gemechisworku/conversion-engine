# Act I harness — execution plan

This document is the single source of truth for implementing the evaluation harness around `tau2-bench` (retail baseline, traces, scores, Langfuse, splits). **Do not modify τ-bench internals** for Act I except an optional one-line env toggle for Langfuse (see §6).

---

## 1. Directory layout (target)

```text
conversion-engine/
├── tau2-bench/                    # pinned upstream; treat as read-only
├── harness/
│   ├── PLAN.md                    # this file
│   ├── README.md                  # quickstart + links here
│   ├── pyproject.toml             # deps: tau2 path, langfuse, pyyaml, etc.
│   ├── config/
│   │   └── baseline.example.yaml  # copy → baseline.yaml (gitignored)
│   ├── schemas/
│   │   ├── score_log.v1.schema.json
│   │   └── trace_log_line.v1.schema.json
│   ├── splits/
│   │   ├── README.md              # staff split contract
│   │   ├── dev_task_ids.json      # 30 ids (from staff or interim)
│   │   └── heldout_task_ids.json  # 20 ids only; no bodies if forbidden
│   ├── src/harness/               # implementation (phased)
│   │   ├── __init__.py
│   │   ├── cli.py                 # typer: run, aggregate, doctor
│   │   ├── config.py              # load baseline.yaml
│   │   ├── runner.py              # invoke tau2 batch / per-sim API
│   │   ├── trace_payload.py       # shared trace + Langfuse simulation JSON
│   │   ├── trace_writer.py        # JSONL append
│   │   ├── score_log.py           # score_log.json read/merge
│   │   ├── metrics.py             # mean, 95% CI, p50/p95
│   │   └── langfuse_sink.py       # optional Langfuse client
│   └── templates/
│       └── baseline.md.j2         # optional ≤400 words skeleton
├── outputs/                       # default artifact dir (gitignored)
│   ├── trace_log.jsonl
│   ├── score_log.json
│   └── runs/                      # optional raw tau2 dumps per run_id
└── baseline.md                    # human deliverable (root or outputs/)
```

---

## 2. Phased implementation

### Phase 0 — Preconditions

- `uv sync` inside `tau2-bench`; `uv run tau2 check-data`.
- `.env`: `OPENROUTER_API_KEY`; any keys LiteLLM needs for pinned agent/user models.
- Record **exact** model strings and CLI-equivalent args in `baseline.yaml` (course pins).

### Phase 1 — Smoke path (one task, one trial)

- Harness calls τ-bench (subprocess `tau2 run` **or** import `run_domain` / batch builder — prefer **Python API** for typed `SimulationRun`).
- Append **one** JSONL line conforming to `schemas/trace_log_line.v1.schema.json`.
- Verify line round-trips JSON parse and contains `simulation` blob.

### Phase 2 — Full dev baseline (30 tasks × 5 trials = 150 sims)

- Load `splits/dev_task_ids.json`; pass `--task-ids` or equivalent filter through the same code path τ-bench uses.
- Fixed `max_concurrency` in config for comparable wall-clock.
- After batch: compute **`mean_success`** (successful tasks / (n_tasks × trials)), **95% CI** (bootstrap over tasks), **`pass@n`**, **cost** (sum `agent_cost` + `user_cost` per sim; document definition), **wall p50/p95** per simulation.
- Append one object to `score_log.json` (`experiments[]` per `score_log.v1.schema.json`).

### Phase 3 — Small-scale reproduction entry

- Second `score_log.json` entry: e.g. 3 tasks × 1 trial, or full 30 × 1 trial — whatever the rubric names “small-scale reproduction check”; keep config embedded for audit.

### Phase 4 — Langfuse

- **Canonical traces:** `trace_log.jsonl` — **one line per task×trial**; default **`trace_simulation_payload: compact`** (same truncated `simulation` JSON as Langfuse span **output**).
- **Langfuse:** `langfuse_sink.py` uses the **identical** `simulation` dict as span **output** (no second truncation path). Optional **`full`** mode stores full `SimulationRun` in both trace and Langfuse.
- Optional: enable LiteLLM → Langfuse via env-driven `USE_LANGFUSE` (§6) for token-level spans **in addition to** harness traces.

### Phase 5 — Held-out wiring (no task bodies)

- `heldout_task_ids.json` (or course path) + `heldout_task_ids_path` in YAML; **`--mode heldout_prepare`** validates ids, disjointness vs dev, and writes **`heldout_prepare_manifest.json`**.
- **`--mode heldout_run`** runs the held-out slice behind **`HARNESS_HELDOUT_RUN=1`**; **`heldout_trace_policy`** (`full` \| `metadata_only` \| `none`) limits **`trace_log.jsonl`** / Langfuse payload shape. Stock τ-bench still loads task definitions in-process — true blind execution needs staff infra; see `README.md`.

### Phase 6 — Deliverables

- `baseline.md` (≤400 words) filled from metrics + anomalies.
- Ensure `score_log.json` has **≥2** experiment records; `trace_log.jsonl` covers **all dev trials**.

---

## 3. Metrics definitions (freeze in README)

| Metric | Definition |
|--------|----------------|
| Success | Default: `simulation.reward_info.reward == 1.0` after normal termination (align with τ-bench early-exit rules). |
| `mean_success` | **(Tasks with ≥1 success) / (n_tasks × trials)** — **[0, 1]**; **`ci95`** bootstraps **tasks**. |
| `pass@n` in score_log | **Percentage (0–100)** of tasks that pass **on try n only** (`trial_index == n-1`). One `pass@n` + `ci95_pass@n` per n up to `num_trials_per_task`; CI bootstraps **tasks**. |
| Cost per run | Recommend **agent + user** USD from τ-bench fields; note `0` if LiteLLM has no price table for model. |
| Wall clock | Time around single `run_simulation` / one CLI invocation; report p50/p95 across sims. |
| 95% CI | **Bootstrap** (preferred for small n) with fixed seed; report `ci_low`, `ci_high`, `B`, `seed`. |

---

## 4. CLI surface (harness)

| Command | Purpose |
|---------|---------|
| `harness doctor` | Checks env keys, tau2 import, data dir, split file presence. |
| `harness run --config baseline.yaml` | Full baseline; writes/append JSONL + updates score log. |
| `harness run --config baseline.yaml --dry-run` | Print resolved task count and commands, no API. |
| `harness aggregate --score-log outputs/score_log.json` | Recompute CIs from existing JSONL (optional). |

---

## 5. Reference baseline (soft target)

- Store **published number** and URL/citation in `score_log` entry under `reference`.
- Note **repo version / commit** of `tau2-bench`; τ³ task fixes may shift scores vs older τ² publications.

---

## 6. Optional τ-bench change (Langfuse env toggle)

**Single change (if you fork or patch):** in `tau2/config.py`, replace `USE_LANGFUSE = False` with reading `os.getenv("TAU2_USE_LANGFUSE", "").lower() in ("1", "true", "yes")`. Then enable without code edits:

```bash
set TAU2_USE_LANGFUSE=true
```

If you must stay **zero-diff** on τ-bench, skip this and use **Langfuse SDK only** in `harness`.

---

## 7. Acceptance checklist (Act I)

- [ ] Pinned models in `baseline.yaml`; same file used for both score_log entries.
- [ ] `trace_log.jsonl`: one line per dev simulation; `simulation` matches Langfuse output (compact or full per config).
- [ ] `score_log.json`: validates against `schemas/score_log.v1.schema.json`; ≥2 experiments.
- [ ] `baseline.md`: word count ≤400; cites CI, cost, anomalies.
- [ ] Langfuse: at least trace metadata per run (and/or LiteLLM callback enabled).
- [ ] No conversion-agent code in critical path for baseline runs.

---

## 8. Open questions for staff / rubric

- **Resolved in harness:** `pass@1` = % tasks passing on first try only; `pass@n` = % passing on try n (see README / `metrics_definitions`).
- Official **30 + 20** task id lists vs upstream 114-task retail.
- Whether **held-out** execution must be blind at the **harness** level or only at grading.
