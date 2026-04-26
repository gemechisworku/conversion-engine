# Act IV Method: Thread-Scoped Context Firewall (TSCF)

## 1) Objective
Reduce `multi_thread_leakage` (selected in `target_failure_mode.md`) by enforcing participant-scoped context isolation before interpretation, drafting, and scheduling actions.

## 2) Root Cause and Mechanism Rationale

Root cause (not surface symptom):
- Current failure occurs because memory is effectively lead/company scoped in multi-contact situations.
- When two contacts are active, retrieval and action planning can mix context across participants.

Why TSCF addresses root cause:
- It changes memory keying and retrieval boundaries so sibling-thread context is unavailable by default.
- It adds ambiguity abstention when participant identity is uncertain.
- It adds a contamination detector that blocks leaks before send/booking.

## 3) Re-Implementable Design Specification

### 3.1 Data contract additions

Add the following fields to conversation and message records:
- `participant_key` (string): normalized channel identity (`email:<lowercase_email>` or `sms:<e164_number>`)
- `thread_key` (string): `"{lead_id}:{participant_key}"`
- `participant_resolution_confidence` (float in `[0,1]`)
- `participant_resolution_method` (`exact|alias|heuristic|unknown`)
- `context_scope` (`participant|lead_fallback`)
- `contamination_score` (float in `[0,1]`)

### 3.2 Participant resolution algorithm

1. Build candidate participants from known identities on `lead_id`.
2. Score each candidate:
- exact channel match = `1.00`
- exact alias match = `0.90`
- heuristic domain/name match = `0.60`
- no reliable match = `0.00`
3. Choose top candidate and set `participant_resolution_confidence`.
4. Apply gate:
- if score `>= 0.85`: proceed with participant-scoped context.
- if `0.60 <= score < 0.85`: ask clarification or escalate (`thread_identity_ambiguous`).
- if `< 0.60`: mandatory escalation, no autonomous draft/send.

### 3.3 Context retrieval policy

For interpretation/drafting/scheduling, retrieve only:
- records where `thread_key` equals active thread
- max `12` most recent turns
- max `1800` prompt tokens of conversation context
- if exceeded: compact oldest turns into structured summary (no sibling-thread merge)

No lead-wide fallback is allowed for outbound generation.

### 3.4 Contamination detector

Run before final draft approval and before booking action.

Inputs:
- active thread entities (names, roles, timezone tokens, objections)
- sibling thread entities for same lead
- candidate outbound message

Detector features:
- foreign-entity hit count (entity appears in sibling but not active thread)
- timezone mismatch flag
- objection-source mismatch flag
- lexical overlap ratio vs sibling-only memory

Decision:
- compute `contamination_score`
- if `contamination_score > 0.30` OR foreign-entity hits `>= 1`:
  - regenerate once with strict context reminder
  - re-check detector
  - if still failing: escalate with reason `cross_thread_contamination`

### 3.5 Policy and state-machine integration

TSCF runs before existing policy checks; existing checks remain mandatory:
- claim validation
- bench commitment checks
- kill switch
- sink routing
- scheduling confirmation rules

State behavior:
- ambiguous participant -> transition to `handoff_required`
- no auto booking without explicit confirmation (unchanged)
- invalid transitions remain blocked per state machine

## 4) Hyperparameters and Thresholds (Actual Values)

| Parameter | Value | Why |
| --- | --- | --- |
| `participant_confidence_high` | `0.85` | Require near-certain identity before autonomous actions |
| `participant_confidence_low` | `0.60` | Below this, heuristic mapping is too risky |
| `max_turns_context` | `12` | Keeps thread context focused while preserving recent intent |
| `max_context_tokens` | `1800` | Cost cap to prevent context pathology |
| `foreign_entity_hit_threshold` | `1` | One sibling-only entity is enough to indicate leakage risk |
| `contamination_score_threshold` | `0.30` | Conservative block threshold |
| `max_regeneration_attempts` | `1` | Avoid runaway loops; escalate quickly |
| `timezone_conflict_threshold` | `2` distinct timezone tokens | Forces clarification in EU/US/EAT mixed threads |
| `booking_requires_explicit_confirmation` | `true` | Maintains dual-control safeguard |
| `sibling_threads_considered` | `5` max | Bound detector cost in high-contact accounts |

## 5) Ablation Variants (Explicit Contrasts)

### A0: Day-1 baseline
- Behavior: lead-scoped retrieval, no participant firewall.
- Tests: baseline failure incidence.

### A1: Partition-only
- Change from A0: add `participant_key` and strict thread-scoped retrieval.
- Removes: ambiguity gate and contamination detector.
- Tests: effect of memory partitioning alone.

### A2: Partition + ambiguity gate
- Change from A1: add confidence thresholds (`0.85/0.60`) and abstain/escalate path.
- Removes: contamination detector.
- Tests: value of identity-confidence control beyond partitioning.

### A3: Full TSCF (final method)
- Change from A2: add contamination detector + one guarded regeneration.
- Tests: incremental value of pre-send/pre-book leak blocking.

## 6) Statistical Test Plan (Prose)

Primary claim (required):
- Delta A = `safe_success(A3) - safe_success(A0)` is positive with `p < 0.05`.

Where:
- `safe_success = 1 - thread_isolation_violation_rate`
- Unit of analysis = held-out task

Procedure:
1. Run A0, A1, A2, A3 on identical held-out tasks with equal compute budget.
2. Compute per-task safe_success for each variant.
3. Bootstrap tasks with replacement (`B=5000`, `seed=42`) to estimate 95% CI for Delta A.
4. Compute one-sided p-value for hypothesis `DeltaA > 0`.
5. Accept if all are true:
- `DeltaA_mean > 0`
- `DeltaA_CI95_low > 0`
- `p < 0.05`

Secondary comparisons:
- Delta B = `A3 - AutoOpt` on same budget (must be explained if negative)
- Delta C = `A3 - tau2_reference` (informational only)

## 7) Implementation Checklist

1. Add `participant_key` and `thread_key` persistence in repository layer.
2. Update runtime retrieval to require active `thread_key`.
3. Add participant-resolution scorer and ambiguity gate in reply/scheduling flow.
4. Add contamination detector before outbound send and booking calls.
5. Add escalation reason codes:
- `thread_identity_ambiguous`
- `cross_thread_contamination`
6. Extend tests with fixtures for:
- two contacts at same company
- sibling-thread timezone conflict
- objection cross-bleed
- wrong-participant booking prevention

## 8) Expected Tradeoffs

- Safety: significant reduction in thread-leakage failures.
- Conversion: minor reduction possible due to more abstentions.
- Cost: slight increase from detector pass + occasional regeneration; bounded by hard limits.

## 9) Output Artifacts

- `method.md` (this file)
- `ablation_results.json` (results schema)
- `held_out_traces.jsonl` (per-task traces)

## 10) Execution Summary (Current Run)

Executed on `2026-04-25` via:
- `python scripts/run_act4_heldout_eval.py`

Key results from `ablation_results.json`:
- `A0 safe_success`: `0.675`
- `A3 safe_success`: `1.000`
- `Delta A (A3 - A0)`: mean `0.324945`, 95% CI `[0.275, 0.375]`, `p=0.0` (one-sided), requirement pass = `true`
- `Delta B (A3 - AutoOpt)`: mean `0.125`, 95% CI `[0.125, 0.125]`, `p=0.0`

Execution mode note:
- These numbers are from a reproducible held-out policy replay simulation over Act III observed probe rates.
- For external benchmark claims, run live sealed-slice evaluation with the same metric definitions.
