## 1. Purpose

Persist normalized lead and conversation state into CRM.

## 2. Responsibilities

* upsert lead data
* append conversation events
* attach brief and booking references
* keep stage synchronized

## 3. Allowed Tools

* crm_upsert_lead
* crm_append_event
* crm_set_stage
* crm_attach_brief_refs
* kb_read_page
* observability tools

## 4. Rules

* MUST use idempotent event keys
* MUST not invent missing values
* MUST preserve external system identifiers

---