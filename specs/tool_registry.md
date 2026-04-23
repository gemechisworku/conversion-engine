## 1. Purpose

This document defines the tool surface exposed to the orchestration layer and subagents. It specifies:

* tool purpose
* ownership
* caller permissions
* request/response contracts
* side effects
* guardrails
* logging requirements

The tool layer MUST present **business-oriented, typed operations** rather than raw vendor SDK calls.

---

## 2. Design Principles

### TR-1. Typed interfaces

Every tool MUST accept and return structured payloads.

### TR-2. Narrow responsibilities

Each tool MUST perform one clearly bounded task.

### TR-3. Policy-enforced execution

Tools with side effects MUST enforce:

* kill switch
* sink routing
* permission scope
* idempotency where applicable

### TR-4. Full traceability

Every tool call MUST emit observability events.

### TR-5. Evidence preservation

Read tools returning claims or extracted facts MUST include source metadata.

---

## 3. Tool Categories

### 3.1 Evidence Tools

Used for public-signal collection and normalization.

#### `fetch_company_profile`

**Purpose**
Retrieve normalized company profile from source dataset.

**Allowed Callers**

* signal-researcher
* lead-orchestrator

**Input**

```json
{
  "company_id": "string",
  "source": "crunchbase"
}
```

**Output**

```json
{
  "company_id": "string",
  "name": "string",
  "domain": "string",
  "industry": "string",
  "size_band": "string",
  "location": "string",
  "funding_summary": {},
  "source_meta": {}
}
```

**Side Effects**
None

**Logging**

* tool_name
* caller
* request_id
* source identifiers
* latency

---

#### `fetch_funding_events`

**Purpose**
Return funding events within requested lookback window.

**Allowed Callers**

* signal-researcher
* competitor-gap-analyst

**Input**

```json
{
  "company_id": "string",
  "window_days": 180
}
```

**Output**

```json
{
  "events": [
    {
      "date": "YYYY-MM-DD",
      "round_type": "Series A",
      "amount_usd": 12000000,
      "source_meta": {}
    }
  ]
}
```

---

#### `fetch_job_posts`

**Purpose**
Collect public job-post evidence and compute velocity inputs.

**Allowed Callers**

* signal-researcher

**Input**

```json
{
  "company_domain": "string",
  "window_days": 60
}
```

**Output**

```json
{
  "current_open_roles": 12,
  "engineering_open_roles": 7,
  "ai_adjacent_roles": 2,
  "velocity_delta_pct": 140.0,
  "roles": [],
  "source_meta": []
}
```

**Guardrails**

* MUST respect robots.txt
* MUST not require login
* MUST not bypass anti-bot controls

---

#### `fetch_layoff_events`

#### `fetch_leadership_changes`

#### `fetch_tech_stack`

#### `fetch_public_ai_signals`

These follow the same pattern:

* read-only
* evidence-returning
* source-backed
* confidence-aware

All MUST return `source_meta`.

---

### 3.2 Knowledge Base Tools

#### `kb_read_page`

**Purpose**
Read a KB page.

**Allowed Callers**

* all agents except outbound-only workers

**Input**

```json
{
  "path": "string"
}
```

**Output**

```json
{
  "path": "string",
  "content": "string",
  "last_updated_at": "timestamp"
}
```

---

#### `kb_write_page`

**Purpose**
Create or update a KB page.

**Allowed Callers**

* signal-researcher
* competitor-gap-analyst
* ai-maturity-scorer
* crm-recorder
* lead-orchestrator

**Input**

```json
{
  "path": "string",
  "content": "string",
  "mode": "replace"
}
```

**Output**

```json
{
  "path": "string",
  "status": "written"
}
```

**Guardrails**

* MUST reject writes outside KB root
* MUST version writes
* MUST append audit entry

---

#### `kb_find_pages`

#### `kb_update_index`

#### `kb_append_log`

Used for retrieval, indexing, and durable research history.

---

### 3.3 Reasoning Support Tools

#### `score_ai_maturity`

**Purpose**
Convert evidence into AI maturity score and explanation.

**Allowed Callers**

* ai-maturity-scorer
* lead-orchestrator

**Input**

```json
{
  "evidence_packet_id": "string"
}
```

**Output**

```json
{
  "score": 2,
  "confidence": 0.71,
  "justifications": [
    {
      "signal": "ai_adjacent_open_roles",
      "weight": "high",
      "evidence_ref": "string"
    }
  ]
}
```

---

#### `classify_icp`

#### `bench_match`

#### `validate_claims`

#### `compute_signal_confidence`

These tools MUST return structured verdicts, not prose-only responses.

`validate_claims` is especially critical and MUST output:

* supported claims
* unsupported claims
* weak claims
* rewrite recommendations

---

### 3.4 Outreach Tools

#### `draft_email`

**Purpose**
Generate a draft email from brief + style profile.

**Allowed Callers**

* lead-orchestrator
* tone-and-claim-reviewer

**Input**

```json
{
  "lead_id": "string",
  "brief_id": "string",
  "template_type": "cold_email",
  "style_profile": "tenacious_default"
}
```

**Output**

```json
{
  "draft_id": "string",
  "subject": "string",
  "body": "string",
  "claim_refs": [],
  "draft_meta": {}
}
```

**Side Effects**
None

---

#### `draft_sms`

#### `queue_email`

#### `queue_sms`

#### `send_email`

#### `send_sms`

**Guardrails for send tools**

* MUST check kill switch
* MUST check sink routing
* MUST ensure review status approved
* MUST attach trace ID
* MUST reject messages lacking lead ID

---

### 3.5 CRM Tools

#### `crm_upsert_lead`

**Purpose**
Create or update a lead record.

**Allowed Callers**

* crm-recorder
* lead-orchestrator

**Input**

```json
{
  "lead": {
    "lead_id": "string",
    "company_id": "string",
    "company_name": "string",
    "segment": "string",
    "confidence": 0.82,
    "ai_maturity": 2
  }
}
```

**Output**

```json
{
  "crm_record_id": "string",
  "status": "upserted"
}
```

---

#### `crm_append_event`

#### `crm_set_stage`

#### `crm_attach_brief_refs`

All CRM tools MUST be idempotent when passed the same event key.

---

### 3.6 Scheduling Tools

#### `get_calendar_slots`

#### `propose_slots`

#### `book_discovery_call`

#### `resolve_timezone`

`book_discovery_call` MUST return booking identifiers and failure reasons when unsuccessful.

---

### 3.7 Policy Tools

#### `check_kill_switch`

**Purpose**
Return whether outbound actions are globally disabled.

**Allowed Callers**

* send tools
* lead-orchestrator
* reviewer

**Output**

```json
{
  "enabled": false,
  "reason": "manual_pause"
}
```

---

#### `check_sink_routing`

#### `check_bench_commitment`

#### `require_human_handoff`

#### `redact_sensitive_content`

These tools are policy-critical and MUST be called before irreversible actions.

---

### 3.8 Observability Tools

#### `log_trace_event`

#### `log_tool_use`

#### `log_subagent_event`

#### `log_compaction_event`

#### `log_business_outcome`

These may write to Langfuse and structured event storage.

---

## 4. Tool Access Matrix

| Tool Category       | Lead Orchestrator | Signal Researcher |    AI Scorer | Competitor Analyst |  ICP Classifier |   Reviewer |             Scheduler | CRM Recorder |
| ------------------- | ----------------: | ----------------: | -----------: | -----------------: | --------------: | ---------: | --------------------: | -----------: |
| Evidence Tools      |              Read |              Read | Limited Read |               Read | Read brief only |         No |                    No |           No |
| KB Tools            |        Read/Write |        Read/Write |   Read/Write |         Read/Write |            Read |       Read |                  Read |   Read/Write |
| Reasoning Tools     |               Yes |           Limited |          Yes |            Limited |             Yes |        Yes |                    No |           No |
| Outreach Tools      |               Yes |                No |           No |                 No |              No | Draft-only | SMS/email reply draft |           No |
| CRM Tools           |           Limited |                No |           No |                 No |              No |         No |               Limited |          Yes |
| Scheduling Tools    |           Limited |                No |           No |                 No |              No |         No |                   Yes |           No |
| Policy Tools        |               Yes |                No |           No |                 No |         Limited |        Yes |                   Yes |          Yes |
| Observability Tools |               Yes |               Yes |          Yes |                Yes |             Yes |        Yes |                   Yes |          Yes |

---

## 5. Tool Execution Rules

### TR-6. Side-effect ordering

For send or booking tools, the system MUST execute in this order:

1. validate state
2. validate policy
3. log intent
4. execute tool
5. log result
6. persist downstream state

### TR-7. Retry policy

Read tools MAY be retried automatically.
Write/send tools MUST use bounded retries and idempotency keys.

### TR-8. Error contracts

All tools MUST return normalized errors:

```json
{
  "error_code": "string",
  "error_message": "string",
  "retryable": true
}
```

### TR-9. Security boundary

No agent may invoke raw third-party SDKs directly. All external access MUST go through registered tools.

## Idempotency Table

| Tool                | Idempotency Required | Idempotency Key                 |
| ------------------- | -------------------- | ------------------------------- |
| crm_upsert_lead     | Yes                  | lead_id                         |
| crm_append_event    | Yes                  | event_key                       |
| crm_set_stage       | Yes                  | lead_id + target_state          |
| queue_email         | Yes                  | draft_id + channel              |
| send_email          | Yes                  | draft_id + delivery_attempt_key |
| queue_sms           | Yes                  | draft_id + channel              |
| send_sms            | Yes                  | draft_id + delivery_attempt_key |
| book_discovery_call | Yes                  | lead_id + slot_id               |
| kb_write_page       | Prefer yes           | path + content_hash             |

## 2. Error Code Table

| Error Code               | Meaning                               | Retryable |
| ------------------------ | ------------------------------------- | --------: |
| INVALID_INPUT            | malformed request                     |        No |
| INVALID_STATE_TRANSITION | illegal state move                    |        No |
| TOOL_TIMEOUT             | external or internal timeout          |       Yes |
| SOURCE_UNAVAILABLE       | upstream source unreachable           |       Yes |
| POLICY_BLOCKED           | action blocked by policy              |        No |
| EVIDENCE_INSUFFICIENT    | insufficient evidence for safe action |        No |
| REVIEW_REQUIRED          | send attempted without approval       |        No |
| DELIVERY_FAILED          | email/SMS provider failure            |       Yes |
| CRM_SYNC_FAILED          | CRM write failed                      |       Yes |
| BOOKING_FAILED           | booking action failed                 |       Yes |
| IDP_CONFLICT             | idempotency conflict                  |        No |
| PERMISSION_DENIED        | caller not allowed to use tool        |        No |

## 3. Retry Guidance

* Read-only fetch tools: exponential backoff, bounded retries
* CRM writes: bounded retries with idempotency
* Delivery tools: bounded retries, never duplicate side effects
* Booking tools: retry only when booking status is not finalized

---