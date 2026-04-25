## 1. Schema

```json
{
  "lead_id": "string",
  "company_id": "string",
  "company_name": "string",
  "company_domain": "string|null",
  "source": "crunchbase",
  "primary_segment": "string|null",
  "alternate_segment": "string|null",
  "segment_confidence": 0.0,
  "ai_maturity_score": 0,
  "ai_maturity_confidence": 0.0,
  "qualification_status": "unknown|candidate|qualified|disqualified|handoff_required",
  "current_state": "new_lead",
  "brief_id": "string|null",
  "gap_brief_id": "string|null",
  "crm_record_id": "string|null",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

---