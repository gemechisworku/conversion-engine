## 1. Purpose

This workflow defines how the system drafts, reviews, approves, and sends outbound messages while preserving evidence grounding, tone, and policy compliance.

---

## 2. Trigger Conditions

This workflow starts when:

* a lead reaches `brief_ready`
* follow-up is due
* a nurture step is scheduled
* scheduling-related outbound is needed

---

## 3. Preconditions

Before drafting, the system MUST have:

* valid `lead_id`
* current session state
* current hiring signal brief
* current classification result
* current policy state
* current bench snapshot if commitment-adjacent messaging is possible

For first-touch email, competitor gap brief SHOULD also be available.

---

## 4. Inputs

```json
{
  "lead_id": "string",
  "variant": "cold_email|followup_email|nurture_email|scheduling_email|scheduling_sms",
  "reason": "string"
}
```

---

## 5. Outputs

Successful completion MUST produce:

* `draft_id`
* `review_id`
* `message_id` if sent
* updated CRM event
* updated session/conversation state
* claim records and evidence links

---

## 6. Primary Actors

* Lead Orchestrator
* Tone and Claim Reviewer
* CRM Recorder
* Scheduler for scheduling-related messages

---

## 7. Workflow Steps

### Step 1. Prepare message context

The Lead Orchestrator MUST:

1. load current lead state
2. load current brief(s)
3. load policy memory
4. load style rules
5. determine message objective
6. determine channel and variant

### Step 2. Draft message

The orchestrator MUST invoke draft generation.

Draft generation MUST:

1. use brief and gap brief if relevant
2. adapt language to confidence
3. avoid unsupported assertions
4. follow Tenacious voice
5. generate claim refs where possible

### Step 3. Review draft

The orchestrator MUST submit the draft to `tone-and-claim-reviewer`.

The reviewer MUST:

1. validate factual claims
2. validate tone
3. validate confidence-sensitive phrasing
4. validate bench-safe language
5. validate policy constraints
6. either:

   * approve
   * approve with edits
   * reject

### Step 4. Apply rewrites if required

If the review result is `approved_with_edits` or `rejected` with rewrite instructions:

1. a revised draft MUST be generated
2. claim validation MUST be rerun
3. final approval MUST be recorded

### Step 5. Run pre-send policy checks

Before sending, the orchestrator or send layer MUST:

1. check kill switch
2. check sink routing
3. check review approval
4. check channel eligibility
5. check state validity
6. ensure idempotency

### Step 6. Queue or send

On pass:

1. queue or send message
2. persist `message_id`
3. update conversation state
4. append CRM event
5. emit `message_queued` and/or `message_sent`

### Step 7. Persist claims

For every factual claim in outbound content:

1. create claim record
2. attach evidence refs
3. attach review ref
4. attach trace ref

---

## 8. Channel Rules

### Email

* primary for first-touch and most qualification
* preferred for research-led messaging

### SMS

* only for warm leads or scheduling coordination
* MUST NOT be used as first cold-contact channel in normal flow

### Voice

* not used by this workflow for autonomous outbound
* handled via discovery booking / human handoff

---

## 9. State Transitions

Allowed transitions:

* `brief_ready -> drafting`
* `drafting -> in_review`
* `in_review -> queued_to_send`
* `queued_to_send -> awaiting_reply`
* `qualifying -> awaiting_reply`
* `scheduling -> awaiting_reply`

---

## 10. Failure Handling

### F-1. Draft rejected

If review rejects the draft:

* draft MUST NOT be sent
* orchestrator MUST revise or escalate
* rejection reason MUST be logged

### F-2. Policy block

If any send precheck fails:

* send MUST be blocked
* policy decision MUST be recorded
* lead state MAY remain unchanged or move to `handoff_required`

### F-3. Delivery failure

If channel provider fails:

* retry according to delivery policy
* record delivery failure
* avoid duplicate sends

---

## 11. Acceptance Criteria

This workflow is acceptable if:

* every outbound message is reviewed
* unsupported claims are blocked
* all sends are logged and traceable
* channel use follows policy
* conversation state updates after send

---