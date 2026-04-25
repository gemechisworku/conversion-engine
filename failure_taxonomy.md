# Failure Taxonomy (Act III)

Source of trigger-rate aggregates:
- `outputs/evidence/act3_probe_replay_20260425/probe_summary.json`
- `N=8` attempts per probe

## 1) Category Taxonomy (Complete, No Orphans)

| Category | Probe IDs | Aggregate trigger rate | Shared failure pattern |
| --- | --- | --- | --- |
| ICP misclassification | `ICP-001, ICP-002, ICP-003, ICP-004` | `8/32 (25.0%)` | Segment precedence/abstention rules are bypassed under conflicting signals. |
| Hiring-signal over-claiming | `SIG-001, SIG-002, SIG-003, SIG-004` | `10/32 (31.25%)` | Weak signals are converted into strong factual claims without confidence-aware language. |
| Bench over-commitment | `BEN-001, BEN-002, BEN-003` | `7/24 (29.17%)` | Staffing promises exceed verified bench availability or authority boundaries. |
| Tone drift from style guide | `TON-001, TON-002, TON-003, TON-004` | `8/32 (25.0%)` | Multi-turn pressure causes drift from Tenacious style and policy boundaries. |
| Multi-thread leakage | `MTL-001, MTL-002, MTL-003, MTL-004, MTL-005` | `13/40 (32.5%)` | Context from one participant thread contaminates another participant thread. |
| Cost pathology | `COST-001, COST-002, COST-003` | `7/24 (29.17%)` | Prompt/context control fails, causing avoidable token and latency spikes. |
| Dual-control coordination | `DCC-001, DCC-002, DCC-003` | `5/24 (20.83%)` | Agent advances actions requiring explicit user/human control confirmation. |
| Scheduling edge cases (EU/US/EAT) | `SCH-001, SCH-002, SCH-003` | `6/24 (25.0%)` | Timezone and temporal references are resolved unsafely under ambiguity. |
| Signal reliability (+ false-positive notes) | `REL-001, REL-002, REL-003` | `5/24 (20.83%)` | Confidence language does not match evidence quality/known false-positive risk. |
| Gap over-claiming | `GAP-001, GAP-002, GAP-003` | `7/24 (29.17%)` | Competitive-gap framing overstates certainty or drifts into condescension. |

Overall trigger rate across all probes: `76/280 (27.14%)`.

## 2) Coverage Integrity Check

### Probe ledger
`ICP-001..004, SIG-001..004, BEN-001..003, TON-001..004, MTL-001..005, COST-001..003, DCC-001..003, SCH-001..003, REL-001..003, GAP-001..003`

### Validation
- Total probes in library: `35`
- Unique probes represented in taxonomy: `35`
- Orphan probes (in library but not taxonomy): `0`
- Duplicate assignments (probe in more than one category): `0`

## 3) Root-Cause Families (for Act IV mechanism mapping)

| Root-cause family | Included probes | Why it matters |
| --- | --- | --- |
| Context partition failure | `MTL-*` | Cross-thread contamination is the dominant source of high-cost trust failures. |
| Evidence calibration failure | `SIG-*`, `REL-*`, `GAP-001`, `GAP-003` | Over-certainty against weak evidence violates grounded-honesty constraints. |
| Authority/commitment boundary failure | `BEN-*`, `DCC-003`, `TON-003` | Out-of-scope commitments create commercial and policy risk. |
| State-control failure | `DCC-001`, `DCC-002`, `SCH-*` | Missing confirmations/timezone clarifications cause execution errors. |
| Style resilience failure | `TON-*`, `GAP-002` | Tone drift under pressure introduces brand and conversion damage. |
| Cost guardrail failure | `COST-*` | Cost-per-lead can degrade quickly without bounded retries/context. |
| Segmentation decision failure | `ICP-*` | Wrong segment selection causes low-fit messaging and thread stall. |

## 4) ROI Candidate Ranking Input

Ranking signal combines observed trigger rate and category severity in Tenacious context:
1. `multi_thread_leakage`
2. `bench_over_commitment`
3. `hiring_signal_over_claiming`
4. `gap_over_claiming`
5. Remaining categories

Detailed arithmetic for target selection is documented in `target_failure_mode.md`.