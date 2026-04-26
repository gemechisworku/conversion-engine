To: Tenacious CEO and CFO  
From: Week 10 conversion-engine evaluation  
Date: 2026-04-25  
Subject: Live-prospect readiness (two-page summary)

---

## Decision (three sentences)

The stack is **strong on benchmarked task success and on the held-out thread-isolation story**, but it is **not yet CFO-grade on commercial proof**: we cannot honestly claim research-led competitor-gap lift or annualized revenue because **live traces show zero research-led first touches** and **approved ACV inputs are still placeholders** in `tenacious_sales_data/seed/baseline_numbers.md`. **Recommendation:** no broad autonomous outbound; if anything runs, use a **30-day supervised Segment 4 pilot** with **human send approval**, **100% outbound variant tags**, and **success / kill metrics** below.

---

## Page 1 — What we can prove from traces and baselines

**τ² retail (baseline harness)** — `baseline.md`, τ² commit `d11a97072c49d093f7b5a3e4fe9da95b490d43ba`  
- pass@1 **72.67%**; 95% CI **65.04%–79.17%**; **150** sims; avg agent cost **$0.0199**; p50/p95 latency **105.95s / 551.65s**.

**Cost per “qualified lead” proxy (held-out replay, method A3)** — `held_out_traces.jsonl`, `ablation_results.json`  
- **160** traces; **$152.05** total `cost_usd` → **$0.9503** per trace.  
- Reply-progressed **143** → **$152.05 / 143 ≈ $1.06** per reply-progressed sim.  
- Booking-progressed **142** → **$152.05 / 142 ≈ $1.07** per booking-progressed sim.  
- **Rig/infra** is not separately metered in these artifacts; treat as **LLM + simulation variable cost**, not fully loaded CAC.

**Stalled-thread delta (definition alignment)**  
- **Manual baseline:** 30–40% stall in first two weeks for engaged/curious replies without a booked discovery call — `tenacious_sales_data/seed/email_sequences/reengagement.md` (cites `baseline_numbers.md`).  
- **System proxy (A3, same numerator shape):** (replied ∧ ¬booked) / replied = **1/143 = 0.70%**; Wilson 95% CI **~0.12%–3.85%**.  
- **Caveat:** held-out rows are **policy replay simulation**, not production CRM; interpret as **directional safety signal**, not proof of production stall rate.

**Competitive-gap / research-led vs generic (live)** — `outputs/runtime_state.db` → `message_log`  
- **5** distinct leads with `first_touch_sent`; **0** first touches classified as competitor-gap / peer-led opener (conservative text check: no peer/sector/top-quartile/competitor framing); **3** inbound replies on those sends → **generic-path reply rate 60%** on **N=5** (not statistically stable).  
- **Research-led vs generic reply delta:** **not measurable** (research-led **N=0**).

**Annualized “deal volume” scenarios (touch math only; $ blocked)**  
- Anchor: **~60** thoughtful touches / rep / week — `baseline_numbers.md`.  
- Touches/year: one segment **3,120**; two **6,240**; four **12,480**.  
- If you apply the **approved** funnel bands in `baseline_numbers.md` (7–12% reply × 30–50% meeting→proposal × 20–30% proposal→close), implied closes/touch/year land in **~0.42%–1.80%**; multiply by the touch counts above for **~13–56 / ~26–112 / ~52–225** deals/year **before** ACV.  
- **Dollar impact:** **blocked** — same file still shows tokens like `$[ACV_MIN]` / `$[PROJECT_ACV_MIN]`; no fabrication.

**Pilot (if approved)**  
- **Segment 4** only; **60** first touches/week; **human-reviewed send**; tag every outbound with **variant + evidence pointers** (spec: `specs/evaluation_and_acceptance.md`).  
- **30-day success:** research-led arm **≥7% reply** on tagged sends with **wrong-signal <5%** (human QA audit).  
- **Weekly AI envelope (rough):** ~60 × **~$1.07** booking-unit proxy ≈ **~$64/week** variable sim cost order-of-magnitude (still not infra-loaded).

---

## Page 2 — Skeptic’s appendix (compressed)

**Four τ²-blind failure modes (concrete)** — `probe_library.md`  
1. **Offshore framing / unauthorized commercial** — `TON-003` (mirrors “offshore rate” pressure; risks tone + policy).  
2. **Hard factual miss** — `SIG-002` (fabricated restructure).  
3. **Bench authority** — `BEN-001` / `BEN-002` (capacity / date promises vs `bench_summary.json`).  
4. **Cross-thread + timezone** — `MTL-002`, `SCH-001` (wrong participant / silent TZ).

**Public-signal lossiness (AI maturity / gap)** — `competitor_gap_brief.schema.json`  
- **False negative:** sophisticated internal work, **low public signal** → score 0–1 → **too-generic** entry, Segment 4 under-used.  
- **False positive:** loud AI-adjacent hiring / launch language → **overstated maturity / overstated gap** → defensive technical buyer.

**Gap-analysis risks (one line each)**  
- **Deliberate non-adoption** — `GAP-002` (“we solved that”) + condescending reply path.  
- **Wrong peer set** — schema allows sub-niche; broad-sector benchmark can be **economically irrelevant**.  
- **Evidence collapse** — `GAP-003`: allowed “no public signal of X”; forbidden “does not do X.”

**Brand tradeoff (uses published bands, not Tenacious ACV)**  
- Baseline table: **1–3%** generic reply vs **7–12%** signal-grounded — `baseline_numbers.md` (sources named there: LeadIQ/Apollo; Clay/Smartlead).  
- **1,000** sends, **5%** wrong-signal → **50** bad emails; gross reply uplift vs 1–3% baseline is **~40–110** replies at 7–12%. **Break-even framing:** wrong-signal cost must stay **below ~0.8–2.2** “lost positive-replies” per wrong email (algebra from those bands); **do not treat as dollars** without ACV.

**One unresolved probe**  
- **`GAP-003`** (absence-of-signal → capability gap) is **not closed** by the Act IV TSCF work, which targeted **multi-thread leakage** (`method.md`, `ablation_results.json` notes).

**Kill switch**  
- **Pause** if **wrong-signal ≥5%** over any **rolling 100** sent emails (audited in QA), **or** any **cross-thread / wrong-participant** send (`MTL-*` class), **or** **KILL_SWITCH_ENABLED** / outbound gate per `specs/security_and_policy.md`, `specs/non_functional_requirements.md` (NFR-31), and `tenacious_sales_data/policy/data_handling_policy.md` Rule 5.

---

*Evidence mapping for auditors: use root `evidence_graph.json` (claims → files / URLs) and this file as the human-readable memo body.*
