## 1. Schema

```json
{
  "draft_id": "string",
  "lead_id": "string",
  "channel": "email|sms",
  "variant": "cold_email|followup_email|scheduling_sms",
  "subject": "string|null",
  "body": "string",
  "claim_refs": ["claim_123"],
  "style_profile": "tenacious_default",
  "review_status": "pending|approved|approved_with_edits|rejected",
  "review_id": "string|null",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

---