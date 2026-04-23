# Task splits (Act I / IV)

## `dev_task_ids.json`

- JSON array of **string** task IDs, length **30** when using the official curriculum split.
- Example shape: `["0", "1", "3"]`
- Source: program staff artifact (preferred). Until delivered, use a **local** interim list for harness wiring only; **do not** claim it matches the official dev slice in `baseline.md`.

## `heldout_task_ids.json`

- JSON array of **20** string task IDs for the sealed held-out slice.
- Per assignment: task **content** may remain undisclosed until Act IV; this repo should store **IDs only** if that is the rule.
- Harness: set **`heldout_task_ids_path`** in `baseline.yaml`, then `harness run --mode heldout_prepare` (manifest + checks) and, when authorized, `HARNESS_HELDOUT_RUN=1` with `--mode heldout_run`. Trace shape is controlled by **`heldout_trace_policy`**.
- **`heldout_task_ids.example.json`** — curriculum-shaped **example** (20 ids) disjoint from the bundled **`dev_task_ids.json`**; replace with staff ids for real scoring.

## Registering a τ-bench split (optional)

If staff provides a full `split_tasks.json` entry, you can add a named split under `tau2-bench/data/tau2/domains/retail/` and pass `--task-split-name`. Otherwise pass **`--task-ids`** from the harness driver for dev-only runs.
