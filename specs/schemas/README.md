## 1. Purpose

This directory defines canonical schema shapes used across the system.

These schemas serve as:

* data contracts between components
* validation targets
* shared object definitions for agents and services
* traceability anchors

---

## 2. Files

* `lead_object.md`
* `hiring_signal_brief.md`
* `competitor_gap_brief.md`
* `ai_maturity_score.md`
* `bench_match.md`
* `outreach_draft.md`
* `conversation_state.md`
* `session_state.md`
* `crm_event.md`
* `booking_event.md`
* `evidence_record.md`
* `trace_event.md`
* `policy_decision.md`

---

## 3. Schema Rules

### S-1. Canonical naming

Field names should remain stable and predictable.

### S-2. No hidden fields

Business-critical fields MUST be declared explicitly.

### S-3. Validation-first design

All major component outputs SHOULD validate against one of these schemas.

### S-4. IDs over nested duplication

Use object refs and IDs where possible to reduce duplication.

---

## 4. Usage Pattern

* agents produce structured outputs aligned to these schemas
* APIs read/write these schema shapes
* workflows move these objects through the system
* observability links events and schema IDs

---