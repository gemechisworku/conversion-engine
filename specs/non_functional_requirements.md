## 1. Purpose

This document defines the non-functional requirements for performance, reliability, cost, safety, maintainability, and operability.

These requirements are binding alongside the functional requirements.

---

## 2. Performance Requirements

### NFR-1. Lead intake latency

The system SHOULD complete lead intake and enrichment within an operationally acceptable window for challenge use.

Suggested target:

* p50 end-to-end enrichment under 2 minutes
* p95 end-to-end enrichment under 5 minutes

### NFR-2. Reply handling latency

Inbound reply interpretation and next-best-action generation SHOULD be responsive enough for near-real-time workflows.

Suggested target:

* p50 reply handling under 15 seconds
* p95 reply handling under 45 seconds

### NFR-3. Scheduling latency

Slot proposal generation SHOULD complete quickly.

Suggested target:

* p50 slot retrieval and response drafting under 10 seconds

### NFR-4. Tool latency observability

Every tool MUST expose latency for p50/p95 reporting.

---

## 3. Reliability Requirements

### NFR-5. Idempotency

All state-mutating operations MUST support idempotency.

### NFR-6. Retry strategy

Read operations MAY be retried automatically.
Write operations MUST use bounded retries and idempotency keys.

### NFR-7. Partial-failure tolerance

The system SHOULD continue operating with partial evidence when safe, while surfacing reduced confidence.

### NFR-8. No silent failure

All failures MUST produce logs and structured error outputs.

### NFR-9. Recovery

The system MUST support recovery after:

* process restart
* context compaction
* temporary integration outage

---

## 4. Cost Requirements

### NFR-10. Cost visibility

The system MUST support per-trace and per-lead cost attribution.

### NFR-11. Budget enforcement

The orchestration layer SHOULD support configurable token and model budget ceilings.

### NFR-12. Cost-aware delegation

Specialized or cheaper models SHOULD be used for lower-risk subagent tasks where quality is acceptable.

### NFR-13. Cost per lead

The design SHOULD optimize toward the challenge target economics and allow reporting of:

* cost per processed lead
* cost per qualified lead

---

## 5. Safety and Compliance Requirements

### NFR-14. Evidence-backed outputs

Outbound content MUST be evidence-backed or clearly softened.

### NFR-15. Policy enforcement

Unsafe actions MUST be blocked before execution.

### NFR-16. Auditability

Every externally visible message MUST be explainable by:

* trace
* review record
* evidence references
* policy decisions

### NFR-17. Data scope compliance

Only approved public/synthetic data may be used during challenge execution.

---

## 6. Maintainability Requirements

### NFR-18. Modular architecture

Agents, tools, workflows, and schemas MUST be modular and independently evolvable.

### NFR-19. Clear contracts

All component boundaries MUST be defined through typed schemas or API contracts.

### NFR-20. Human-readable knowledge

The KB MUST remain inspectable and editable by humans.

### NFR-21. Versioning

Policy memory, KB pages, and specs SHOULD be versioned.

---

## 7. Observability Requirements

### NFR-22. Full tracing

Every lead-processing run MUST produce a trace.

### NFR-23. Event completeness

All key state transitions and tool calls MUST be logged.

### NFR-24. Claim traceability

Every factual claim in an external message MUST map to evidence refs.

### NFR-25. Metric derivability

The logs MUST be sufficient to compute business and system KPIs.

---

## 8. Security and Access Requirements

### NFR-26. Tool scoping

Agents MUST only access tools granted to them.

### NFR-27. Side-effect isolation

External side effects MUST occur only through approved tools.

### NFR-28. Least privilege

Subagents SHOULD be granted the minimum tool access required.

---

## 9. Operability Requirements

### NFR-29. Manual override

The system SHOULD support safe human override at key decision points.

### NFR-30. Dry-run capability

The system SHOULD support dry-run mode for testing and evaluation.

### NFR-31. Kill switch

A kill switch MUST exist for outbound actions.

### NFR-32. Sink routing

Challenge-mode outbound MUST support sink routing and make it observable.

---

## 10. Quality Requirements

### NFR-33. Tone consistency

The system SHOULD maintain consistent brand tone across turns.

### NFR-34. Robustness to ambiguity

The system SHOULD prefer clarification or escalation over unsafe certainty.

### NFR-35. Context boundedness

The system MUST keep active context bounded through memory layering and compaction.

---

## 11. Acceptance Criteria

Non-functional requirements are acceptable if:

* measured performance is reportable
* failures are recoverable and visible
* costs are attributable
* side effects are controlled
* traces and audits are complete

---