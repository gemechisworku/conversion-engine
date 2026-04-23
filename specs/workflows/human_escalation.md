## 1. Purpose

This workflow defines how the system packages and routes cases that should not be handled autonomously.

---

## 2. Trigger Conditions

Escalation begins when:

* pricing is out of scope
* legal/compliance questions appear
* evidence is materially insufficient
* state inconsistency is detected
* tone/policy risk remains unresolved
* a human-only discovery step is reached
* manual escalation is requested

---

## 3. Preconditions

Before escalation, the system MUST have:

* `lead_id`
* escalation reason code
* current lead and conversation state
* relevant evidence/brief refs
* current trace context

---

## 4. Inputs

```json
{
  "lead_id": "string",
  "reason_code": "string",
  "reason_summary": "string",
  "triggered_by": "system|human",
  "evidence_refs": []
}
```

---

## 5. Outputs

Successful escalation MUST produce:

* `handoff_id`
* handoff package
* CRM event
* updated lead state
* observable escalation record

---

## 6. Primary Actors

* Lead Orchestrator
* Human Handoff Coordinator
* CRM Recorder

---

## 7. Workflow Steps

### Step 1. Freeze unsafe autonomous action

The orchestrator MUST:

* stop any pending unsafe send or booking action
* mark the lead as `handoff_required` if appropriate

### Step 2. Gather context

The system MUST collect:

* lead summary
* current stage
* last inbound/outbound summary
* classification result
* brief refs
* gap brief refs
* policy decision refs
* unresolved questions
* recommended next action

### Step 3. Build handoff package

The Human Handoff Coordinator MUST create:

* handoff summary
* reason code
* urgency
* current state snapshot
* relevant evidence links
* suggested response path

### Step 4. Persist and notify

The system MUST:

* persist `handoff_id`
* append CRM event
* log escalation event
* assign or expose to human queue

### Step 5. Resolve handoff state

When a human takes over or resolves:

* update handoff state
* optionally update lead state
* preserve audit trail

---

## 8. Handoff Package Schema

```json
{
  "handoff_id": "string",
  "lead_id": "string",
  "reason_code": "pricing_out_of_scope",
  "reason_summary": "Prospect asked for detailed staffing and discount structure.",
  "current_state": "handoff_required",
  "conversation_summary": "Warm prospect, likely qualified, pricing requested.",
  "recommended_next_action": "Human sales lead should respond with scoped pricing discussion.",
  "refs": {
    "brief_id": "brief_123",
    "gap_brief_id": "gap_456",
    "classification_id": "class_789",
    "policy_decision_ids": ["pol_123"]
  },
  "created_at": "timestamp"
}
```

---

## 9. Acceptance Criteria

This workflow is acceptable if:

* unsafe automation stops when escalation triggers
* humans receive a complete package
* escalation is visible in CRM and traces
* no context needed by the human is lost

---