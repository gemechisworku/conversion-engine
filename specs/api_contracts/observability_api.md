## 1. Purpose

Defines event ingestion and trace-support API contracts.

---

## 2. Endpoints

## `POST /trace/event`

### Request

```json
{
  "event_type": "tool_call_succeeded",
  "trace_id": "trace_123",
  "lead_id": "lead_123",
  "payload": {}
}
```

## `POST /trace/claim`

### Request

```json
{
  "claim_id": "claim_123",
  "lead_id": "lead_123",
  "claim_text": "string",
  "evidence_refs": ["ev_123"],
  "review_id": "review_123",
  "trace_id": "trace_123"
}
```

---