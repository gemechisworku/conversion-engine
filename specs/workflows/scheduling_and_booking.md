## 1. Purpose

This workflow defines how the system handles scheduling coordination, slot proposals, confirmation, and booking creation.

---

## 2. Trigger Conditions

This workflow starts when:

* a prospect asks for times
* the orchestrator determines scheduling is the next best action
* a prospect selects a proposed slot

---

## 3. Preconditions

Before booking, the system MUST have:

* `lead_id`
* scheduling intent or confirmation
* current timezone context or a strategy to resolve it
* access to calendar tools
* trace context

---

## 4. Inputs

```json
{
  "lead_id": "string",
  "channel": "email|sms",
  "scheduling_intent": "propose_slots|confirm_slot|clarify_timezone",
  "timezone": "string|null",
  "selected_slot_id": "string|null"
}
```

---

## 5. Outputs

Successful completion MUST produce:

* proposed slots or confirmed booking
* booking ID if booked
* outbound scheduling message if needed
* updated scheduling context
* CRM update
* trace events

---

## 6. Primary Actors

* Scheduler
* Lead Orchestrator
* CRM Recorder

---

## 7. Workflow Steps

### Step 1. Resolve timezone

The Scheduler MUST:

1. use explicit prospect timezone when available
2. otherwise infer cautiously from signals or prior messages
3. if ambiguous, ask a clarification question instead of assuming aggressively
4. log timezone assumption source

### Step 2. Retrieve slots

The Scheduler MUST:

1. retrieve candidate availability
2. apply calendar constraints
3. produce a bounded set of options
4. record slot generation event

### Step 3. Propose slots

If no slot is yet selected:

1. generate reply with slots
2. send via correct channel
3. update scheduling context to `pending`

### Step 4. Confirm booking

If slot selected and confirmation exists:

1. validate slot availability
2. create booking
3. record `booking_id`
4. update CRM
5. update conversation state

### Step 5. Handle booking outcome

If booking succeeds:

* move lead toward `booked`

If booking fails:

* return recovery options
* retry or propose new slots
* escalate if state becomes inconsistent

---

## 8. Rules

* the system MUST NOT book without explicit prospect confirmation
* timezone assumptions MUST be logged
* scheduling via SMS is allowed only after warm engagement
* booking confirmation MUST be persisted before state closes

---

## 9. State Transitions

* `qualifying -> scheduling`
* `scheduling -> awaiting_reply`
* `scheduling -> booked`
* `scheduling -> handoff_required`

---

## 10. Acceptance Criteria

This workflow is acceptable if:

* timezone ambiguity is handled safely
* slot proposals are persisted
* bookings produce IDs and CRM updates
* booking failures do not corrupt state

---