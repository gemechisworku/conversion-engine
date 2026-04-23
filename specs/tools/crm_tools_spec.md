## 1. Purpose

Defines CRM integration tools.

## 2. Tool Set

* `crm_upsert_lead`
* `crm_append_event`
* `crm_set_stage`
* `crm_attach_brief_refs`

## 3. Rules

* CRM writes must be idempotent
* CRM state should reflect lead state, not replace it as source-of-truth
* missing fields must not be hallucinated

---