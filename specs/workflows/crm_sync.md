## 1. Purpose

Defines how lead state and major events are synchronized into CRM.

## 2. Trigger Examples

* lead created
* state transition
* brief generated
* message sent
* reply received
* booking confirmed
* handoff created

## 3. Rules

* CRM updates must be idempotent
* CRM is downstream projection, not source-of-truth
* failures must be retried safely and logged

---
