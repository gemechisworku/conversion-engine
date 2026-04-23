## 1. Purpose

This directory defines service-level contracts between system components.

These files are intended to support:

* backend API implementation
* test generation
* runtime validation
* integration boundary clarity

---

## 2. Files

* `orchestration_api.md`
* `research_api.md`
* `scoring_api.md`
* `outreach_api.md`
* `crm_api.md`
* `scheduling_api.md`
* `kb_api.md`
* `memory_api.md`
* `observability_api.md`
* `policy_api.md`

---

## 3. Contract Rules

### API-1. Structured envelopes

All endpoints SHOULD use a consistent response envelope.

### API-2. Request traceability

All mutating endpoints MUST support `request_id` and/or idempotency keys.

### API-3. Explicit failure

All failures MUST use normalized error payloads.

### API-4. No schema drift

Responses MUST align with `schemas/*`.

---

## 4. How to Use

* Implement services directly from these docs
* Use schemas for request/response validation
* Map workflow steps to these APIs
* Add versioning when externalizing beyond the challenge environment

---