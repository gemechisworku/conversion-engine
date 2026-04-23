## 1. Schema

```json
{
  "policy_decision_id": "string",
  "lead_id": "string|null",
  "policy_type": "kill_switch|sink_routing|bench_commitment|claim_validation|escalation",
  "decision": "pass|fail|blocked|escalate",
  "reason": "string",
  "evidence_refs": [],
  "trace_id": "string",
  "created_at": "timestamp"
}
```

---
