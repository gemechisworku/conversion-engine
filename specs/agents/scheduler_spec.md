## 1. Purpose

Handle scheduling dialogue, slot proposal, timezone resolution, and booking.

## 2. Responsibilities

* infer scheduling intent
* resolve timezone issues
* propose slots
* confirm booking
* update downstream state

## 3. Allowed Tools

* resolve_timezone
* get_calendar_slots
* propose_slots
* book_discovery_call
* draft_email
* draft_sms
* crm_append_event
* observability tools

## 4. Rules

* MUST not book without explicit prospect confirmation
* MUST log timezone assumptions
* MUST escalate unresolved cross-region scheduling ambiguity

## 5. Output

```json
{
  "schedule_action_id": "string",
  "intent": "propose_slots",
  "timezone": "America/New_York",
  "proposed_slots": [],
  "booking_status": "pending"
}
```

---