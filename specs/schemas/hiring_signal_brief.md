## 1. Purpose

Defines the structure of the hiring signal brief used by the orchestrator, reviewer, and outreach generation.

---

## 2. Schema

```json
{
  "brief_id": "string",
  "lead_id": "string",
  "company_id": "string",
  "generated_at": "timestamp",
  "primary_segment_hypothesis": "string|null",
  "signals": {
    "funding_event": {
      "present": true,
      "summary": "Raised Series A in last 180 days",
      "confidence": 0.92,
      "evidence_refs": ["ev_funding_123"]
    },
    "job_post_velocity": {
      "present": true,
      "summary": "Engineering roles increased materially over 60 days",
      "confidence": 0.78,
      "evidence_refs": ["ev_jobs_123"]
    },
    "layoffs": {
      "present": false,
      "summary": "No qualifying layoff event found",
      "confidence": 0.67,
      "evidence_refs": []
    },
    "leadership_change": {
      "present": false,
      "summary": "No recent CTO/VP Engineering change found",
      "confidence": 0.54,
      "evidence_refs": []
    },
    "tech_stack": {
      "present": true,
      "summary": "Public stack suggests modern data tooling",
      "confidence": 0.61,
      "evidence_refs": ["ev_stack_123"]
    }
  },
  "ai_maturity": {
    "score": 2,
    "confidence": 0.64,
    "justification_refs": ["ev_ai_123"]
  },
  "bench_match": {
    "status": "partial_match",
    "confidence": 0.71,
    "required_skills": ["python", "data"],
    "available_skills": ["python", "ml"],
    "notes": []
  },
  "research_hook": {
    "summary": "Recent funding plus engineering hiring suggests scale pressure.",
    "confidence": 0.76
  },
  "language_guidance": {
    "tone_mode": "assertive_but_softened",
    "allowed_claim_types": [],
    "disallowed_claim_types": [],
    "must_soften": true
  },
  "risk_notes": [
    "Job-post evidence is moderate rather than strong."
  ]
}
```

---

## 3. Field Rules

* every signal MUST include `confidence`
* every asserted factual signal SHOULD include `evidence_refs`
* `language_guidance.must_soften` MUST be true when evidence confidence falls below configured thresholds
* `bench_match` MUST reflect real bench state, not inferred availability
* `risk_notes` MUST capture material ambiguity

---

## 4. Acceptance Criteria

The brief schema is acceptable if it can support:

* outreach generation
* review and policy checking
* evidence linking
* memo traceability

---