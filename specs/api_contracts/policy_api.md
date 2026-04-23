## 1. Purpose

Defines contracts for evaluating policy gates and recording policy decisions.

---

## 2. Endpoints

## `POST /policy/check`

### Request

```json
{
  "lead_id": "lead_123",
  "policy_type": "bench_commitment",
  "context": {}
}
```

### Response

```json
{
  "request_id": "req_701",
  "trace_id": "trace_701",
  "status": "success",
  "data": {
    "decision": "pass",
    "reason": "No capacity claim present in draft."
  },
  "error": null,
  "timestamp": "timestamp"
}
```

## `POST /policy/decision`

Persist a policy decision record.

---