## 1. Purpose

Defines contracts for draft generation, review, queueing, and send actions.

---

## 2. Endpoints

## `POST /outreach/draft`

### Request

```json
{
  "lead_id": "lead_123",
  "brief_id": "brief_123",
  "gap_brief_id": "gap_123",
  "variant": "cold_email"
}
```

### Response

```json
{
  "request_id": "req_401",
  "trace_id": "trace_401",
  "status": "success",
  "data": {
    "draft_id": "draft_123",
    "subject": "string",
    "body": "string"
  },
  "error": null,
  "timestamp": "timestamp"
}
```

## `POST /outreach/review`

### Request

```json
{
  "lead_id": "lead_123",
  "draft_id": "draft_123"
}
```

### Response

```json
{
  "request_id": "req_402",
  "trace_id": "trace_402",
  "status": "success",
  "data": {
    "review_id": "review_123",
    "status": "approved_with_edits",
    "final_send_ok": true
  },
  "error": null,
  "timestamp": "timestamp"
}
```

## `POST /outreach/send`

### Request

```json
{
  "lead_id": "lead_123",
  "draft_id": "draft_123",
  "review_id": "review_123",
  "channel": "email"
}
```

### Response

```json
{
  "request_id": "req_403",
  "trace_id": "trace_403",
  "status": "success",
  "data": {
    "message_id": "msg_123",
    "delivery_status": "queued"
  },
  "error": null,
  "timestamp": "timestamp"
}
```

### Guardrails

* MUST fail if no approved review exists
* MUST fail if kill switch blocks outbound
* MUST fail if sink routing policy is not satisfied when required

---