## 1. Purpose

This document defines the formal state machines for the core runtime entities in the system. It exists to:

* constrain orchestration behavior
* prevent invalid transitions
* support deterministic API validation
* simplify debugging and recovery
* improve traceability

State machines MUST be treated as source-of-truth for runtime progression.

---

## 2. Design Rules

### SM-1. Explicit states only

No implicit or inferred state transitions are allowed in production logic.

### SM-2. Guarded transitions

Every transition MUST define:

* trigger
* preconditions
* actor
* side effects
* failure behavior

### SM-3. Invalid transitions are errors

All invalid transitions MUST be rejected and logged.

### SM-4. Terminal states

Terminal states MUST be explicit and must not silently reopen without a defined recovery path.

---

## 3. Lead Lifecycle State Machine

## 3.1 States

* `new_lead`
* `enriching`
* `brief_ready`
* `drafting`
* `in_review`
* `queued_to_send`
* `awaiting_reply`
* `reply_received`
* `qualifying`
* `scheduling`
* `booked`
* `nurture`
* `handoff_required`
* `disqualified`
* `closed`

## 3.2 Transition Table

### `new_lead -> enriching`

**Trigger**

* new lead intake started

**Actor**

* Lead Orchestrator

**Preconditions**

* valid company_id
* trace initialized

**Side Effects**

* create session state
* create trace
* emit `lead_created`

---

### `enriching -> brief_ready`

**Trigger**

* enrichment, scoring, competitor brief, and classification completed successfully or within acceptable partial thresholds

**Actor**

* Lead Orchestrator

**Preconditions**

* evidence packet exists
* brief exists
* score exists
* classification exists or abstention recorded

**Side Effects**

* attach refs to lead object
* update CRM
* emit `brief_generated`

---

### `brief_ready -> drafting`

**Trigger**

* outreach generation requested

**Actor**

* Lead Orchestrator

**Preconditions**

* current policy state loaded
* lead not blocked
* lead not disqualified

**Side Effects**

* create draft task
* emit `draft_created` on completion

---

### `drafting -> in_review`

**Trigger**

* draft created

**Actor**

* Lead Orchestrator

**Preconditions**

* draft_id exists

**Side Effects**

* invoke reviewer

---

### `in_review -> queued_to_send`

**Trigger**

* reviewer approved or approved_with_edits

**Actor**

* Lead Orchestrator

**Preconditions**

* review_id exists
* final_send_ok = true

**Side Effects**

* queue send
* emit `message_queued`

---

### `queued_to_send -> awaiting_reply`

**Trigger**

* message send/queue accepted

**Actor**

* Lead Orchestrator or delivery subsystem

**Preconditions**

* message_id exists

**Side Effects**

* update conversation state
* append CRM event
* emit `message_sent`

---

### `awaiting_reply -> reply_received`

**Trigger**

* inbound message received

**Actor**

* Lead Orchestrator

**Preconditions**

* inbound message recorded

**Side Effects**

* update conversation state
* emit `reply_received`

---

### `reply_received -> qualifying`

**Trigger**

* next-best-action = continue qualification or answer clarification

**Actor**

* Lead Orchestrator

**Preconditions**

* reply intent interpreted

**Side Effects**

* create response or internal qualification update

---

### `reply_received -> scheduling`

**Trigger**

* prospect indicates scheduling intent

**Actor**

* Lead Orchestrator

**Preconditions**

* scheduling intent detected

**Side Effects**

* invoke Scheduler

---

### `qualifying -> scheduling`

**Trigger**

* prospect is sufficiently qualified and ready to book

**Actor**

* Lead Orchestrator

**Preconditions**

* qualification threshold met

**Side Effects**

* update qualification status
* invoke Scheduler

---

### `scheduling -> booked`

**Trigger**

* booking confirmed

**Actor**

* Scheduler / Lead Orchestrator

**Preconditions**

* booking_id exists
* prospect confirmation exists

**Side Effects**

* CRM update
* conversation state update
* emit `booking_confirmed`

---

### `qualifying -> nurture`

**Trigger**

* prospect interested but timing not right

**Actor**

* Lead Orchestrator

**Preconditions**

* no active disqualifying block

**Side Effects**

* create follow-up action
* record nurture reason

---

### `any -> handoff_required`

**Trigger**

* escalation required

**Actor**

* Lead Orchestrator / Human Handoff Coordinator

**Preconditions**

* escalation reason recorded

**Side Effects**

* create handoff package
* update CRM
* emit `handoff_triggered`

---

### `any -> disqualified`

**Trigger**

* lead determined to be non-ICP or clearly unsuitable

**Actor**

* Lead Orchestrator

**Preconditions**

* evidence-backed disqualification reason

**Side Effects**

* update lead qualification status
* stop outreach actions

---

### `booked -> closed`

**Trigger**

* discovery booking completed and ownership transferred

**Actor**

* Lead Orchestrator / CRM Recorder

**Preconditions**

* booking confirmed
* handoff complete if required

**Side Effects**

* mark workflow complete

---

## 3.3 Invalid Transitions

Examples of invalid transitions:

* `awaiting_reply -> booked`
* `new_lead -> awaiting_reply`
* `disqualified -> queued_to_send`
* `closed -> drafting`
* `handoff_required -> send_message` without explicit human override

All invalid transitions MUST return `INVALID_STATE_TRANSITION`.

---

## 4. Conversation State Machine

## 4.1 States

* `no_conversation`
* `outbound_prepared`
* `outbound_sent`
* `waiting`
* `inbound_received`
* `clarifying`
* `objection_handling`
* `scheduling_dialogue`
* `declined`
* `nurture_pending`
* `handoff_pending`
* `completed`

## 4.2 Key transitions

* `no_conversation -> outbound_prepared`
* `outbound_prepared -> outbound_sent`
* `outbound_sent -> waiting`
* `waiting -> inbound_received`
* `inbound_received -> clarifying`
* `inbound_received -> objection_handling`
* `inbound_received -> scheduling_dialogue`
* `inbound_received -> declined`
* `scheduling_dialogue -> completed`
* `any -> handoff_pending`

Conversation state MUST remain consistent with lead lifecycle state.

---

## 5. Scheduling State Machine

## 5.1 States

* `none`
* `timezone_unknown`
* `slots_requested`
* `slots_proposed`
* `prospect_selecting`
* `booking_pending`
* `booking_confirmed`
* `booking_failed`
* `handoff_required`

## 5.2 Transition examples

* `none -> timezone_unknown`
* `timezone_unknown -> slots_requested`
* `slots_requested -> slots_proposed`
* `slots_proposed -> prospect_selecting`
* `prospect_selecting -> booking_pending`
* `booking_pending -> booking_confirmed`
* `booking_pending -> booking_failed`
* `booking_failed -> slots_requested`
* `any -> handoff_required`

The system MUST NOT enter `booking_confirmed` without:

* explicit prospect confirmation
* booking_id
* successful calendar response

---

## 6. Review State Machine

## 6.1 States

* `not_started`
* `pending_review`
* `approved`
* `approved_with_edits`
* `rejected`
* `blocked_by_policy`

## 6.2 Rules

* `approved` and `approved_with_edits` are send-eligible only if policy checks also pass
* `rejected` MUST not send
* `blocked_by_policy` MUST not send and SHOULD escalate if unresolved

---

## 7. Handoff State Machine

## 7.1 States

* `not_required`
* `required`
* `package_prepared`
* `assigned`
* `acknowledged`
* `resolved`
* `closed`

## 7.2 Rules

A handoff MUST include:

* reason code
* summary
* current lead/conversation state
* relevant refs
* recommended next step

---

## 8. Acceptance Criteria

State machines are acceptable if:

* all major runtime flows have explicit transitions
* invalid transitions are blocked
* recovery paths exist for failures
* API and workflow specs can validate against these states

---