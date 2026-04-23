## 1. Schema

```json
{
  "gap_brief_id": "string",
  "lead_id": "string",
  "company_id": "string",
  "generated_at": "timestamp",
  "comparison_set": [
    {
      "company_name": "string",
      "reason_included": "same sector and size band",
      "ai_maturity_score": 2,
      "confidence": 0.61
    }
  ],
  "sector_percentile": 0.0,
  "top_quartile_practices": [
    {
      "practice": "Hiring dedicated ML platform roles",
      "evidence_refs": ["ev_321"]
    }
  ],
  "missing_practices": [
    {
      "practice": "No public evidence of ML platform hiring",
      "confidence": 0.58,
      "evidence_refs": ["ev_654"]
    }
  ],
  "language_guidance": {
    "avoid_condescension": true,
    "frame_as_observation": true
  },
  "confidence": 0.0,
  "risk_notes": []
}
```

---