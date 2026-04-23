## 1. Purpose

This document defines the API contract for the orchestration layer that coordinates lead processing, conversation handling, state transitions, and agent delegation.

---

## 2. API Design Rules

### OA-1. Typed request/response

All endpoints MUST use structured JSON.

### OA-2. Traceability

Every request and response MUST contain:

* request_id
* trace_id or trace initiation details

### OA-3. Idempotency

Endpoints that create or transition lead state MUST support idempotency keys.

### OA-4. Explicit failure mode

All failures MUST return normalized error objects.

---

## 3. Common Response Envelope

```json
{
  "request_id": "string",
  "trace_id": "string",
  "status": "success|accepted|failure",
  "data": {},
  "error": null,
  "timestamp": "timestamp"
}
```

---

## 4. Endpoints

## 4.1 `POST /lead/process`

Start end-to-end processing for a new lead.

### Request

```json
{
  "idempotency_key": "string",
  "company_id": "string",
  "source": "crunchbase",
  "priority": "normal",
  "metadata": {
    "initiated_by": "system"
  }
}
```

### Response

```json
{
  "request_id": "req_123",
  "trace_id": "trace_123",
  "status": "accepted",
  "data": {
    "lead_id": "lead_123",
    "state": "enriching"
  },
  "error": null,
  "timestamp": "2026-04-23T12:00:00Z"
}
```

### Behavior

This endpoint MUST:

* create or resolve a lead record
* initiate enrichment workflow
* create top-level trace

---

## 4.2 `POST /lead/reply`

Submit an inbound reply for an existing lead.

### Request

```json
{
  "idempotency_key": "string",
  "lead_id": "lead_123",
  "channel": "email",
  "message_id": "msg_123",
  "content": "Can you share times next week?",
  "received_at": "timestamp"
}
```

### Response

```json
{
  "request_id": "req_124",
  "trace_id": "trace_124",
  "status": "accepted",
  "data": {
    "lead_id": "lead_123",
    "state": "reply_received",
    "next_action": "schedule"
  },
  "error": null,
  "timestamp": "2026-04-23T12:05:00Z"
}
```

### Behavior

This endpoint MUST:

* persist inbound message
* update conversation state
* trigger reply handling flow

---

## 4.3 `POST /lead/advance`

Advance a lead explicitly to the next valid state.

### Request

```json
{
  "idempotency_key": "string",
  "lead_id": "lead_123",
  "from_state": "brief_ready",
  "to_state": "drafting",
  "reason": "enrichment and classification completed"
}
```

### Response

```json
{
  "request_id": "req_125",
  "trace_id": "trace_125",
  "status": "success",
  "data": {
    "lead_id": "lead_123",
    "current_state": "drafting"
  },
  "error": null,
  "timestamp": "2026-04-23T12:06:00Z"
}
```

### Guardrails

* MUST reject invalid transitions
* MUST log state transition event

---

## 4.4 `GET /lead/{lead_id}/state`

Return the current normalized state for a lead.

### Response

```json
{
  "request_id": "req_126",
  "trace_id": "trace_126",
  "status": "success",
  "data": {
    "lead_id": "lead_123",
    "state": "awaiting_reply",
    "segment": "recently_funded_startup",
    "segment_confidence": 0.74,
    "ai_maturity_score": 2,
    "pending_actions": [],
    "kb_refs": [],
    "policy_flags": []
  },
  "error": null,
  "timestamp": "2026-04-23T12:07:00Z"
}
```

---

## 4.5 `POST /lead/escalate`

Escalate a lead to human review.

### Request

```json
{
  "idempotency_key": "string",
  "lead_id": "lead_123",
  "reason_code": "pricing_out_of_scope",
  "summary": "Prospect requested detailed staffing quote.",
  "evidence_refs": ["brief_123", "msg_123"]
}
```

### Response

```json
{
  "request_id": "req_127",
  "trace_id": "trace_127",
  "status": "success",
  "data": {
    "lead_id": "lead_123",
    "state": "handoff_required",
    "handoff_id": "handoff_123"
  },
  "error": null,
  "timestamp": "2026-04-23T12:08:00Z"
}
```

---

## 4.6 `POST /lead/compact`

Compact working context for an active lead.

### Request

```json
{
  "lead_id": "lead_123",
  "reason": "context_threshold_exceeded"
}
```

### Response

```json
{
  "request_id": "req_128",
  "trace_id": "trace_128",
  "status": "success",
  "data": {
    "lead_id": "lead_123",
    "compaction_ref": "compact_123",
    "current_state": "awaiting_reply"
  },
  "error": null,
  "timestamp": "2026-04-23T12:09:00Z"
}
```

---

## 4.7 `POST /lead/rehydrate`

Reconstruct working context for a lead.

### Request

```json
{
  "lead_id": "lead_123"
}
```

### Response

```json
{
  "request_id": "req_129",
  "trace_id": "trace_129",
  "status": "success",
  "data": {
    "lead_id": "lead_123",
    "rehydrated_state_ref": "rehydrated_123",
    "current_state": "reply_received"
  },
  "error": null,
  "timestamp": "2026-04-23T12:10:00Z"
}
```

---

## 5. Error Contract

```json
{
  "request_id": "req_err_123",
  "trace_id": "trace_err_123",
  "status": "failure",
  "data": {},
  "error": {
    "error_code": "INVALID_STATE_TRANSITION",
    "error_message": "Cannot transition from awaiting_reply to booked directly.",
    "retryable": false
  },
  "timestamp": "2026-04-23T12:11:00Z"
}
```

---

## 6. State Validation Rules

The API layer MUST enforce:

* valid lead state transitions
* lead existence for mutating endpoints
* required IDs
* idempotency for repeat submissions
* policy-compatible execution for actioning endpoints

---

## 7. Acceptance Criteria

The orchestration API is acceptable if:

* new leads can be started reliably
* replies can resume the workflow
* invalid transitions are rejected
* compaction/rehydration can be triggered cleanly
* escalations are represented explicitly

---