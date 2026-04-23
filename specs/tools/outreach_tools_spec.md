## 1. Purpose

Defines tools related to drafting, queueing, and sending outbound communications.

## 2. Tool Set

* `draft_email`
* `draft_sms`
* `queue_email`
* `queue_sms`
* `send_email`
* `send_sms`

## 3. Rules

* no send without review for required channels
* no send without policy check
* no send without trace linkage
* every send must map to lead_id and draft_id

---