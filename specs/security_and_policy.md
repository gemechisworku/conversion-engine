## 1. Purpose

This document defines mandatory guardrails, approval rules, and operational safety constraints for the system.

The policy layer exists to protect:

* Tenacious brand integrity
* data-handling compliance
* communication safety
* business authority boundaries
* traceability and auditability

---

## 2. Policy Principles

### P-1. Groundedness first

The system MUST NOT present unsupported factual claims as facts.

### P-2. Limited authority

The system MUST NOT commit staffing, pricing, or legal terms beyond defined scope.

### P-3. Public-data-only during challenge

The system MUST only use allowed public or provided synthetic data sources.

### P-4. Human escalation on uncertainty

The system MUST escalate rather than bluff when authority or evidence is insufficient.

### P-5. Reversible actions preferred

For side-effecting actions, the system SHOULD prefer queue/review/confirm over irreversible execution.

---

## 3. Core Policy Areas

## 3.1 Evidence and claim policy

The system MUST:

* link factual claims to evidence
* downgrade weak evidence into suggestive language
* reject unsupported statements
* distinguish absence of evidence from evidence of absence

The system MUST NOT:

* fabricate hiring pressure
* exaggerate AI maturity
* invent leadership changes
* assert competitor gaps without supporting analysis

---

## 3.2 Bench commitment policy

The system MUST:

* check current bench state before any staffing-adjacent claim
* avoid explicit or implicit capacity commitments unless permitted

The system MUST NOT:

* promise named staffing availability
* imply immediate staffing without confirmation
* claim exact match when only partial match exists

Allowed language examples:

* “There may be a fit based on the kinds of teams we support.”
* “We can explore whether the current bench aligns with your needs.”

Blocked language examples:

* “We have the exact team available right now for your stack.”
* “We can start a 5-person Python squad next week.”

---

## 3.3 Pricing policy

The system MAY:

* reference public-tier pricing bands if explicitly allowed
* speak at a high level about engagement shapes

The system MUST NOT:

* quote deep custom pricing
* negotiate terms
* commit discounts
* produce final proposals autonomously

Requests beyond allowed pricing scope MUST trigger escalation.

---

## 3.4 Channel policy

* Email is the default outbound channel
* SMS is restricted to warm leads and scheduling
* Voice is not used for autonomous cold outreach in standard flow

The system MUST NOT:

* initiate cold outreach by SMS unless an explicit approved exception exists
* switch channels in ways that feel intrusive or inconsistent with context

---

## 3.5 Tone and brand policy

The system MUST:

* maintain Tenacious voice
* avoid spammy or manipulative language
* keep confidence-sensitive phrasing aligned with evidence
* avoid condescension in competitor-gap messaging
* avoid “offshore language” that creates unnecessary friction

The system MUST NOT:

* shame the prospect
* overstate certainty
* use aggressive fear-based framing
* sound like mass automation when avoidable

---

## 3.6 Data-handling policy

The system MUST:

* operate only on synthetic/public data during challenge execution
* keep draft outputs marked appropriately where required
* preserve deletion and retention expectations
* document kill-switch routing behavior

The system MUST NOT:

* import real customer data outside allowed channels
* distribute restricted seed materials outside policy
* disable sink routing by default

---

## 3.7 Kill-switch policy

A kill switch MUST exist for outbound actions.

When kill switch is active:

* send operations MUST be blocked
* queue operations MAY also be blocked depending on environment
* policy decision MUST be logged
* current work MAY continue in dry-run mode

---

## 3.8 Sink-routing policy

Challenge-mode outbound MUST default to sink routing when required.

The system MUST:

* verify sink routing before side-effecting sends
* log sink-routing decisions
* expose routing mode in observability

---

## 3.9 Escalation policy

The system MUST escalate when:

* evidence is materially insufficient
* pricing is out of scope
* legal/compliance questions appear
* bench commitment risk exists
* contradictory state appears
* tone risk persists after rewrite
* prospect intent cannot be answered safely

Escalation packages MUST include:

* summary
* reason code
* current state
* relevant evidence refs
* recommended next action

---

## 4. Policy Enforcement Points

Policy MUST be enforced at these points:

* before draft approval
* before send
* before booking
* before CRM stage transitions with business significance
* during compaction if pending actions could become unsafe
* during rehydration if stale policy flags exist

---

## 5. Policy Decision Schema

All policy decisions SHOULD map to `schemas/policy_decision.md`.

Minimum fields:

* policy type
* decision
* reason
* evidence refs
* trace ID
* timestamp

---

## 6. Violations and Responses

### Minor violation

Example:

* weak but non-material phrasing issue
  Response:
* rewrite required
* do not send until fixed

### Major violation

Example:

* unsupported claim in outbound
* blocked staffing commitment
* unauthorized pricing quote
  Response:
* block action
* log policy failure
* escalate if needed

### Critical violation

Example:

* kill switch bypass attempt
* non-sink outbound in challenge mode
* use of prohibited data
  Response:
* hard block
* emit alert
* require operator intervention

---

## 7. Acceptance Criteria

The policy system is acceptable if:

* unsafe sends are blocked
* weak-evidence language is softened
* out-of-scope requests escalate cleanly
* kill switch and sink routing are always checked before send
* policy decisions are auditable

---
