## 1. Purpose

This document defines how the system is evaluated for engineering readiness and challenge success.

It covers:

* technical acceptance
* business acceptance
* safety acceptance
* traceability acceptance
* benchmark compatibility

---

## 2. Evaluation Categories

### EA-1. Functional completeness

Does the system implement the required workflows?

### EA-2. System quality

Does it meet non-functional expectations?

### EA-3. Safety and policy

Does it block unsafe behavior?

### EA-4. Evidence integrity

Can claims be traced to evidence?

### EA-5. Business usefulness

Does it improve outreach quality and progression?

### EA-6. Benchmark compatibility

Can it produce the logs and evidence needed for challenge deliverables?

---

## 3. Minimum Acceptance Gates

The system MUST satisfy all of the following:

### Gate A. Lead processing

A new lead can move from:
`new_lead -> enriching -> brief_ready`

### Gate B. Outbound generation

A first-touch email can be:

* drafted
* reviewed
* policy-checked
* sent or queued safely

### Gate C. Reply handling

An inbound reply can:

* update state
* determine next-best-action
* generate safe continuation or scheduling

### Gate D. Scheduling

A warm lead can receive slots and confirm a booking.

### Gate E. CRM synchronization

Key lead and conversation events are reflected in CRM.

### Gate F. Observability

Each run produces trace + event logs.

### Gate G. Policy safety

Unsafe sends are blocked.

### Gate H. Memory continuity

Lead work can resume after compaction or restart.

---

## 4. Acceptance Test Matrix

## 4.1 Lead Intake Tests

* create lead from valid company
* reject invalid source
* continue with partial evidence and lowered confidence
* abstain on contradictory segment signals

## 4.2 Outreach Tests

* generate cold email from valid brief
* reject draft with unsupported claims
* block send with active kill switch
* block SMS as cold first-touch by default

## 4.3 Reply Handling Tests

* classify interest reply correctly
* handle objection without over-claiming
* escalate pricing request
* ask timezone clarification when ambiguous

## 4.4 Scheduling Tests

* propose slots after warm reply
* require explicit confirmation before booking
* recover after unavailable slot
* record booking in CRM

## 4.5 Memory Tests

* compact after long context
* rehydrate lead state correctly
* preserve pending action queue
* preserve policy flags and refs

## 4.6 Observability Tests

* every tool call logged
* claim records created for outbound factual claims
* trace IDs propagate through workflow
* cost and latency derivable

---

## 5. Business Acceptance Criteria

The system SHOULD demonstrate:

* evidence-grounded outreach quality
* reduced risk of stalled-thread behavior
* strong tone consistency
* usable research briefs
* clear human handoff when needed

The system MUST support reporting for:

* reply-rate by outbound variant
* stalled-thread rate
* cost per qualified lead
* booking outcomes
* human handoff rate

---

## 6. Safety Acceptance Criteria

The system is safe enough for challenge use if:

* unsupported factual claims are blocked
* bench over-commitment is blocked
* out-of-scope pricing escalates
* kill switch and sink routing are enforced
* policy decisions are auditable

---

## 7. Evidence Integrity Acceptance

The system passes evidence integrity if:

* every major factual message claim has evidence refs
* final memo numbers can map to traces/evidence
* brief summaries retain confidence values
* unsupported competitor-gap claims are rejected

---

## 8. Benchmark and Deliverable Compatibility

The system MUST be able to produce or support:

* `trace_log.jsonl`
* `score_log.json`
* `held_out_traces.jsonl`
* `evidence_graph.json`
* latency and cost summaries
* outbound variant tags for performance comparison

---

## 9. Exit Criteria

The system is acceptable for implementation/pilot preparation when:

* all minimum acceptance gates pass
* no critical policy gap remains
* traces are complete
* core workflows can be demonstrated end-to-end

---