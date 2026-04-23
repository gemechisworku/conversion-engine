## 1. Purpose

This document describes the logical data model of the system and the main persistent stores.

---

## 2. Storage Domains

### 2.1 Operational State Store

Stores mutable live state required for orchestration.

Objects:

* lead records
* session state
* conversation state
* pending actions
* handoff state

Suggested storage:

* relational DB or document store

---

### 2.2 Knowledge Base Store

Stores durable research artifacts and human-readable markdown.

Objects:

* company pages
* briefs
* gap analyses
* sector notes
* objections
* bench snapshots
* indexes
* logs

Suggested storage:

* filesystem repo or versioned object store

---

### 2.3 Observability Store

Stores traces, events, claim refs, policy decisions, and metrics-supporting records.

Objects:

* traces
* spans
* trace events
* claim records
* policy decisions
* compaction events

Suggested storage:

* Langfuse + structured DB/JSONL

---

### 2.4 Integration State Store

Stores normalized refs to external systems.

Objects:

* CRM IDs
* booking IDs
* message IDs
* delivery status refs
* webhook correlation IDs

---

## 3. Core Tables / Collections

### 3.1 Leads

Fields:

* lead_id
* company_id
* company_name
* domain
* current_state
* qualification_status
* primary_segment
* alternate_segment
* segment_confidence
* ai_maturity_score
* ai_maturity_confidence
* brief_id
* gap_brief_id
* crm_record_id
* created_at
* updated_at

---

### 3.2 Session State

Fields:

* lead_id
* current_stage
* next_best_action
* current_objective
* brief_refs
* kb_refs
* pending_actions
* policy_flags
* handoff_required
* updated_at

---

### 3.3 Conversation State

Fields:

* lead_id
* current_channel
* last_inbound_message_id
* last_outbound_message_id
* last_customer_intent
* last_customer_sentiment
* qualification_status
* objections
* scheduling_context
* updated_at

---

### 3.4 Evidence Records

Fields:

* evidence_id
* company_id
* signal_type
* summary
* source_name
* source_url
* snippet
* fetched_at
* confidence
* raw_ref

---

### 3.5 Hiring Signal Briefs

Fields:

* brief_id
* lead_id
* company_id
* generated_at
* signals
* ai_maturity
* bench_match
* language_guidance
* risk_notes

---

### 3.6 Competitor Gap Briefs

Fields:

* gap_brief_id
* lead_id
* company_id
* generated_at
* comparison_set
* sector_percentile
* missing_practices
* confidence
* risk_notes

---

### 3.7 AI Maturity Scores

Fields:

* score_id
* company_id
* score
* confidence
* signals
* generated_at

---

### 3.8 Outreach Drafts

Fields:

* draft_id
* lead_id
* channel
* variant
* subject
* body
* claim_refs
* review_status
* review_id
* created_at
* updated_at

---

### 3.9 Reviews

Fields:

* review_id
* draft_id
* status
* issues
* required_rewrites
* final_send_ok
* created_at

---

### 3.10 Messages

Fields:

* message_id
* lead_id
* channel
* direction
* provider_ref
* delivery_status
* draft_id
* sent_at
* received_at

---

### 3.11 Bookings

Fields:

* booking_id
* lead_id
* slot_id
* start_at
* end_at
* timezone
* status
* confirmed_by_prospect
* calendar_ref

---

### 3.12 Policy Decisions

Fields:

* policy_decision_id
* lead_id
* policy_type
* decision
* reason
* evidence_refs
* trace_id
* created_at

---

### 3.13 Claim Records

Fields:

* claim_id
* lead_id
* claim_text
* evidence_refs
* review_id
* trace_id
* approved
* created_at

---

### 3.14 Handoff Packages

Fields:

* handoff_id
* lead_id
* reason_code
* reason_summary
* current_state
* conversation_summary
* refs
* created_at
* resolved_at

---

## 4. Versioning Rules

The following SHOULD be versioned:

* policy memory files
* KB pages
* briefs
* gap briefs
* scoring outputs when materially changed

---

## 5. Data Integrity Rules

* all foreign refs must resolve or be explicitly nullable
* active lead state must match state machine
* sent messages must reference approved drafts
* bookings must reference explicit confirmation path
* policy blocks must be preserved

---