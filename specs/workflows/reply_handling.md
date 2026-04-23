## 1. Purpose

This workflow defines how inbound replies are processed, interpreted, and converted into safe next actions.

---

## 2. Trigger Conditions

This workflow begins when:

* an email reply is received
* an SMS reply is received
* a manual message import occurs

---

## 3. Preconditions

Before processing a reply, the system MUST have:

* `lead_id`
* message content
* current lead state
* current conversation state
* access to recent message history
* trace context

---

## 4. Inputs

```json
{
  "lead_id": "string",
  "channel": "email|sms",
  "message_id": "string",
  "content": "string",
  "received_at": "timestamp"
}
```

---

## 5. Outputs

Successful reply handling MUST produce:

* updated conversation state
* updated qualification status
* next best action
* CRM event
* optional draft reply
* optional scheduling handoff
* optional escalation

---

## 6. Primary Actors

* Lead Orchestrator
* Scheduler
* Tone and Claim Reviewer if outbound response is needed
* CRM Recorder
* Human Handoff Coordinator when necessary

---

## 7. Workflow Steps

### Step 1. Record inbound message

The system MUST:

1. persist inbound content
2. attach message metadata
3. append CRM event
4. emit `reply_received`

### Step 2. Rehydrate context

The orchestrator MUST:

1. load current session state
2. load conversation state
3. load recent outbound context
4. load unresolved questions
5. load policy flags if present

### Step 3. Interpret intent

The orchestrator MUST classify reply intent into one of:

* interest
* clarification
* objection
* schedule
* decline
* unclear

This interpretation MUST be persisted.

### Step 4. Determine next best action

Based on intent and current state, the orchestrator MUST choose one:

* answer clarification
* continue qualification
* propose scheduling
* nurture
* disqualify
* escalate to human
* request clarification

### Step 5. Handle branch

#### Branch A. Clarification

* draft response
* review it
* send if approved

#### Branch B. Objection

* consult objection KB if available
* draft response or nurture path
* review it
* send or schedule follow-up

#### Branch C. Scheduling intent

* delegate to scheduler
* propose slots or confirm slot

#### Branch D. Decline

* mark appropriately
* stop active outreach
* optionally put into nurture or closed state

#### Branch E. Unclear

* ask clarifying question
* keep language soft
* avoid assumptions

### Step 6. Update state

After reply handling, the system MUST update:

* conversation stage
* qualification status
* last customer intent
* pending actions
* CRM record
* session state

---

## 8. State Transition Examples

* `awaiting_reply -> reply_received`
* `reply_received -> qualifying`
* `reply_received -> scheduling`
* `reply_received -> nurture`
* `reply_received -> disqualified`
* `reply_received -> handoff_required`

---

## 9. Escalation Conditions

The reply MUST be escalated when:

* the prospect requests pricing beyond policy
* legal or contractual language is requested
* contradiction in prior system state is discovered
* the system cannot answer safely
* the sentiment/tone risk is high
* the request implies a commitment outside authority

---

## 10. Acceptance Criteria

This workflow is acceptable if:

* every reply updates state
* intent is recorded
* next-best-action is explicit
* risky replies are escalated
* no unsafe auto-response is sent

---