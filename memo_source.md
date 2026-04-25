To: Tenacious CEO and CFO
From: Week 10 conversion-engine evaluation
Date: 2026-04-25
Subject: Decision memo on live-prospect readiness

DECISION

The system is promising on safety, but it is not yet decision-grade on
commercial lift. It posts a tau2 retail pass@1 of 72.67% with a 95% CI of
65.04% to 79.17% across 150 simulations, and the Act IV A3 traces reduce the
stalled-thread equivalent to 0.70% (1 stalled thread out of 143 replied
threads; Wilson 95% CI 0.12% to 3.85%) versus the current Tenacious manual
baseline of 30% to 40%. I do not recommend broad live outbound yet because the
committed live traces contain zero research-led competitor-gap first touches
and the approved ACV sheet is still tokenized, so the two CFO questions that
matter most, "does research-led outreach lift replies?" and "what is the
annualized dollar upside?", cannot be answered honestly from this checkout.

TAU2 RETAIL BASELINE

- tau2 retail pass@1: 0.7267, 95% CI [0.6504, 0.7917], 150 simulations.
- Avg agent cost: $0.0199. p50 latency: 105.95s. p95 latency: 551.65s.
- Provenance: `baseline.md`, tau2 commit `d11a97072c49d093f7b5a3e4fe9da95b490d43ba`.

COST PER QUALIFIED LEAD

- A3 held-out traces: 160 simulations, total variable spend $152.05, average
  spend $0.9503 per simulation (`held_out_traces.jsonl`, `ablation_results.json`).
- Reply-progressed lead-equivalent cost:
  $152.05 / 143 = $1.06.
- Booking-progressed lead-equivalent cost:
  $152.05 / 142 = $1.07.
- Caveat: this checkout does not separately meter rig or infra cost. Treat
  $1.06 to $1.07 as LLM-plus-simulation variable cost, not a fully loaded CAC.

STALLED-THREAD RATE DELTA

- Manual Tenacious baseline: 30% to 40% of qualified conversations stall in the
  first two weeks (`tenacious_sales_data/seed/email_sequences/reengagement.md`).
- System trace rate on A3: replied but not booked = 1 / 143 = 0.70%.
- 95% CI on the system rate: 0.12% to 3.85%.
- Improvement versus manual: 29.30 to 39.30 percentage points, or a 97.7% to
  98.3% relative reduction.
- Math:
  stalled_rate = (reply_progressed AND NOT booking_progressed) / reply_progressed

COMPETITIVE-GAP OUTBOUND PERFORMANCE

- Live runtime DB evidence: 5 unique first-touch sends, 0 research-led
  competitor-gap openers, 5 generic hiring-signal openers, 3 replies.
- Research-led share of live outbound: 0%.
- Reply-rate delta between research-led and generic variants: not measurable
  from committed traces because the research-led arm has N = 0.
- CEO/CFO implication: the system has not yet earned the claim that a
  research-led peer-gap opener outperforms a generic Tenacious pitch.

ANNUALIZED IMPACT SCENARIOS

- Capacity anchor: one SDR-equivalent week is about 60 thoughtful touches
  (`tenacious_sales_data/seed/baseline_numbers.md`).
- Funnel assumptions already approved in `seed/baseline_numbers.md`:
  7% to 12% reply for signal-grounded outbound, 30% to 50%
  discovery-to-proposal, 20% to 30% proposal-to-close.
- Implied close rate from outbound touch to closed deal:
  7% to 12% x 30% to 50% x 20% to 30% = 0.42% to 1.80%.
- One segment only: 3,120 touches/year -> about 13 to 56 deals/year.
- Two segments: 6,240 touches/year -> about 26 to 112 deals/year.
- All four segments: 12,480 touches/year -> about 52 to 225 deals/year.
- Dollar impact is blocked. The only approved ACV source in this checkout,
  `tenacious_sales_data/seed/baseline_numbers.md`, still resolves to placeholder
  tokens such as `$[ACV_MIN]` and `$[PROJECT_ACV_MIN]`. I will not fabricate a
  CFO forecast from unresolved ACV inputs.

PILOT RECOMMENDATION

- If you approve any live test, make it a 30-day supervised pilot in
  Segment 4 only. That is the segment where the competitor-gap brief is most
  central, so it is the fastest way to answer the missing commercial question.
- Scope: 60 first touches per week, all human-reviewed before send.
- Variable AI budget ceiling: about $64 per week, using the measured $1.07
  booking-progressed lead-equivalent cost as the conservative unit cost.
- One success criterion after 30 days:
  the research-led variant must clear a 7% reply rate while the wrong-signal
  rate stays below 5%, with 100% outbound variant tagging on every send.

<!-- PAGEBREAK -->

SKEPTIC'S APPENDIX

FAILURE MODES TAU2 DOES NOT CAPTURE

1. Offshore-language failure. In the `TON-003` probe, the prospect pushes on
   price and the agent is tempted to mirror "offshore rate" language or make an
   unauthorized discounting move. That can offend an in-house hiring manager and
   create brand damage even if the thread keeps moving.

2. Unsupported restructuring claim. In `SIG-002`, there is no layoff or
   restructure evidence, but the agent is asked to mention one anyway. A false
   restructuring claim is exactly the kind of factual miss that gets screenshotted.

3. Bench over-commitment. In `BEN-001` and `BEN-002`, the prospect asks for a
   team size or start date that the actual bench summary does not support. tau2
   retail does not test Tenacious-specific staffing authority boundaries.

4. Cross-thread scheduling contamination. In `MTL-002` and `SCH-001`, the agent
   silently reuses one participant's timezone or context for another participant.
   That produces a wrong booking suggestion even when the message looks fluent.

PUBLIC-SIGNAL LOSSINESS

A quietly sophisticated but silent company looks like this system's false
negative: low public AI hiring, few explicit AI titles, little or no AI blog
content, and therefore an AI maturity score of 0 or 1 even though internal
capability is real. In that state the agent softens into a generic exploratory
pitch, underweights Segment 4, and leaves a real consulting opportunity on the
table.

A loud but shallow company looks like the mirror-image false positive: many
AI-adjacent roles, launch language in press, and enough public noise to score as
AI maturity 2 or 3 without strong proof of durable practice. In that state the
agent overstates maturity, overstates the peer gap, and risks a defensive reply
from a technical buyer who knows the internal reality does not match the public
story.

GAP-ANALYSIS RISKS

Risk one: deliberate non-adoption. A top-quartile practice can be a bad
benchmark when the prospect has made an intentional decision not to follow it.
`GAP-002` captures the case: "we already solved that internally." If the agent
pushes anyway, the message lands as condescension, not insight.

Risk two: bad peer set. The competitor-gap schema explicitly allows narrowing to
sub-niche because a broad sector benchmark can be wrong for a narrow operating
model. If the prospect is an AdTech SSP and the benchmark comes from a broader
MarTech or FinTech peer set, the claimed "gap" may simply be irrelevant to the
buyer's actual delivery economics.

Risk three: absence-of-signal error. `GAP-003` is the clean example. The schema
allows "no public signal of X" but forbids "the prospect does not do X." If the
agent collapses that distinction, it turns missing evidence into a false claim.

BRAND-REPUTATION TRADEOFF

The published Tenacious baseline says generic cold outbound replies at 1% to 3%,
while signal-grounded outbound can reach 7% to 12%. On 1,000 emails that is a
gross uplift of 40 to 110 additional replies. At a 5% wrong-signal rate, 50 of
those 1,000 emails are factually wrong.

Break-even is simple: the signal-grounded approach is worth it only if each
wrong-signal email costs less than 0.8 to 2.2 future positive replies. Under an
explicit midpoint assumption of one lost future positive reply per wrong-signal
email, the net result is minus 10 replies in the low case, plus 60 in the high
case, and plus 25 at the midpoint. That is not a comfortable enough margin to
run unsupervised.

ONE HONEST FAILURE

`GAP-003` remains unresolved from the Day 4 probe library. The current Act IV
method targets multi-thread leakage; it does not prove that the system has fixed
the "absence of public signal becomes capability gap" failure. If deployed
anyway, the most likely impact is a research-led opener that sounds specific,
but is wrong in exactly the way a skeptical CTO notices immediately.

KILL-SWITCH CLAUSE

Pause the system immediately if the wrong-signal rate reaches 5% or more over
any rolling window of 100 sent emails. That threshold matches the reputation
stress test above and is easy for Tenacious to audit in QA review.
