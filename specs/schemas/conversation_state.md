## 1. Purpose

This schema defines the normalized state of a lead conversation across email, SMS, and scheduling interactions.

---

## 2. Schema

```json
{
  "lead_id": "string",
  "conversation_state_id": "string",
  "current_stage": "awaiting_reply",
  "current_channel": "email",
  "last_inbound_message_id": "string|null",
  "last_outbound_message_id": "string|null",
  "last_customer_intent": "unknown|interest|clarification|objection|schedule|decline|silent",
  "last_customer_sentiment": "positive|neutral|negative|uncertain",
  "qualification_status": "unknown|likely_qualified|qualified|needs_human_review|disqualified",
  "open_questions": [
    {
      "question": "Do they prefer SMS for scheduling?",
      "owner": "lead-orchestrator"
    }
  ],
  "pending_actions": [
    {
      "action_id": "string",
      "action_type": "followup_email",
      "status": "pending",
      "scheduled_at": "timestamp|null"
    }
  ],
  "objections": [
    {
      "type": "timing",
      "summary": "Not ready this quarter",
      "resolved": false
    }
  ],
  "scheduling_context": {
    "timezone": "string|null",
    "slots_proposed": [],
    "booking_status": "none|pending|confirmed|failed"
  },
  "policy_flags": [],
  "updated_at": "timestamp"
}
```

---

## 3. Field Rules

* `current_stage` MUST align with lead lifecycle state
* `last_customer_intent` MUST be updated on each inbound reply
* `pending_actions` MUST only contain open future work
* `policy_flags` MUST capture unresolved safety issues
* `scheduling_context.booking_status` MUST reflect actual booking outcome

---