# Target Failure Mode (Act III -> Act IV)

## Selected Failure Mode
`multi_thread_leakage`

Definition:
When multiple prospects at the same company are active, the agent leaks facts, objections, timezone assumptions, or booking context from one participant thread into another.

## Why This Wins ROI (Compared Against Alternatives)

Compared categories:
- Candidate A: `multi_thread_leakage`
- Candidate B: `bench_over_commitment`
- Candidate C: `hiring_signal_over_claiming`

Input evidence:
- Act III aggregate trigger rates from `failure_taxonomy.md`
- Tenacious baselines from `tenacious_sales_data/seed/baseline_numbers.md`
- Stalled-thread baseline from `tenacious_sales_data/seed/email_sequences/reengagement.md`

### 1) Exposure term (from probes)
- A (`multi_thread_leakage`) = `13/40 = 32.5%`
- B (`bench_over_commitment`) = `7/24 = 29.17%`
- C (`hiring_signal_over_claiming`) = `10/32 = 31.25%`

### 2) Revenue-at-risk arithmetic (Tenacious terms)

Use only allowed Tenacious/public baselines:
- Stalled qualified-thread baseline: `30% to 40%`
- Discovery-call-to-proposal: `30% to 50%`
- Proposal-to-close: `20% to 30%`
- Talent outsourcing ACV floor: `$[ACV_MIN]`

For `Q = 100` qualified threads (normalization unit):

1. Stalled threads:
`stalled = Q * [0.30, 0.40] = [30, 40]`

2. Leakage-affected stalled threads (A):
`affected_A = stalled * 0.325 = [9.75, 13.0]`

3. Downstream close probability from discovery:
`p_close = [0.30, 0.50] * [0.20, 0.30] = [0.06, 0.15]`

4. Monthly floor revenue at risk from leakage:
`risk_A_month = affected_A * p_close * [ACV_MIN]`
`= [9.75, 13.0] * [0.06, 0.15] * [ACV_MIN]`
`= [0.585, 1.95] * [ACV_MIN]`

5. Annualized floor risk:
`risk_A_year = 12 * risk_A_month = [7.02, 23.4] * [ACV_MIN]`

Interpretation:
Even at floor ACV, leakage has a large annualized revenue-at-risk band, before adding brand damage and recovery labor.

### 3) Alternative comparison arithmetic

A normalized ROI priority score is used for selection:
`ROI_score = trigger_rate * severity_weight * cross_stage_multiplier`

Weights are explicit policy/business assumptions:
- Severity weight:
  - A leakage = `1.00` (trust + booking integrity failures)
  - B bench over-commitment = `0.90` (severe but often pre-send blocked)
  - C over-claiming = `0.70` (often recoverable via rewrite)
- Cross-stage multiplier:
  - A = `1.00` (impacts qualification, scheduling, and booking)
  - B = `0.60` (primarily commitment stage)
  - C = `0.70` (mostly messaging quality stage)

Computed scores:
- A: `0.325 * 1.00 * 1.00 = 0.325`
- B: `0.2917 * 0.90 * 0.60 = 0.1575`
- C: `0.3125 * 0.70 * 0.70 = 0.1531`

Result:
`multi_thread_leakage` is selected because it has the highest combined exposure and cross-stage business damage.

## Non-Revenue Costs Included in Selection

- Brand reputation risk: style guide explicitly warns a single public bad-thread screenshot can outweigh short-term reply gains.
- Recovery cost: leakage incidents usually force manual handoff and thread repair, reducing SDR throughput.
- Scheduling impact: wrong-context scheduling increases no-show and re-coordination overhead.

## Observable Failure Signatures (Act IV success target)

1. Reply references facts not present in active participant thread.
2. Timezone/slot assumptions copied from sibling thread.
3. Booking confirmation generated for the wrong participant context.
4. Escalation reason code indicates identity ambiguity that was ignored.

## Primary Act IV Metric

`thread_isolation_violation_rate`

Act IV acceptance criterion on Delta A:
- `safe_success = 1 - thread_isolation_violation_rate`
- `DeltaA = safe_success(method) - safe_success(day1)`
- Pass if `DeltaA > 0`, `CI95_low > 0`, and `p < 0.05`.