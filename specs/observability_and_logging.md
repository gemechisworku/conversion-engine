## 1. Purpose

This document defines the observability, tracing, event logging, and audit requirements for the system.

The system MUST support:

* debugging
* evaluation
* business analytics
* evidence traceability
* cost attribution
* postmortem analysis

---

## 2. Observability Goals

### O-1. Full lifecycle visibility

Every meaningful lead and agent action MUST be observable.

### O-2. Evidence traceability

Every factual claim used in outreach or memo outputs MUST be traceable to source evidence.

### O-3. Cost visibility

The system MUST support per-lead and per-trace cost measurement.

### O-4. Safety visibility

Policy checks, blocks, and escalations MUST be logged.

### O-5. Evaluation compatibility

Logs MUST support:

* τ²-Bench reporting
* challenge evidence graph creation
* latency reporting
* outbound variant analysis

---

## 3. Logging Backends

## 3.1 Primary Trace Backend

**Langfuse** SHOULD be used for:

* model traces
* spans
* generation metadata
* cost/tokens
* latency
* trace hierarchy

## 3.2 Structured Event Store

A structured event store MUST be maintained in JSONL, database tables, or both for:

* business events
* state transitions
* policy decisions
* tool calls
* subagent boundaries
* compaction records

## 3.3 Evidence Graph Store

A dedicated evidence linkage layer MUST map:

* claims
* evidence refs
* trace IDs
* brief IDs
* source records
* memo/report numbers

---

## 4. Event Taxonomy

## 4.1 Session Events

* `session_started`
* `session_resumed`
* `session_ended`

## 4.2 Agent Lifecycle Events

* `agent_invoked`
* `agent_completed`
* `subagent_started`
* `subagent_completed`
* `subagent_failed`

## 4.3 Tool Events

* `tool_call_started`
* `tool_call_succeeded`
* `tool_call_failed`

## 4.4 Memory Events

* `memory_written`
* `kb_updated`
* `compaction_started`
* `compaction_completed`
* `rehydration_completed`

## 4.5 Business Workflow Events

* `lead_created`
* `lead_enrichment_started`
* `lead_enrichment_completed`
* `brief_generated`
* `gap_brief_generated`
* `classification_completed`
* `draft_created`
* `draft_reviewed`
* `message_queued`
* `message_sent`
* `reply_received`
* `qualification_updated`
* `slot_proposed`
* `booking_confirmed`
* `crm_synced`
* `handoff_triggered`
* `lead_disqualified`

## 4.6 Policy Events

* `policy_check_passed`
* `policy_check_failed`
* `kill_switch_checked`
* `sink_routing_checked`
* `bench_commitment_blocked`
* `send_blocked`
* `escalation_required`

---

## 5. Required Fields for Every Event

All events MUST include:

```json
{
  "event_id": "string",
  "event_type": "string",
  "timestamp": "timestamp",
  "trace_id": "string",
  "lead_id": "string|null",
  "company_id": "string|null",
  "agent_name": "string|null",
  "subagent_name": "string|null",
  "request_id": "string|null",
  "status": "success|failure|blocked|pending",
  "payload": {},
  "error": null
}
```

---

## 6. Trace Structure

## 6.1 Top-Level Trace

Each lead-processing run MUST create a top-level trace.

### Trace Attributes

* trace_id
* lead_id
* company_id
* run_type
* trigger_source
* start_time
* end_time
* total_cost
* total_tokens
* total_latency_ms
* outcome

## 6.2 Nested Spans

Nested spans SHOULD include:

* enrichment
* research subagents
* scoring
* classification
* drafting
* review
* send
* reply handling
* scheduling
* CRM sync
* compaction

---

## 7. Tool Logging Requirements

For every tool call, the system MUST log:

* tool name
* caller agent
* input checksum or normalized args
* start/end time
* latency
* result status
* output identifiers
* retry count
* policy checks if relevant

### Example

```json
{
  "event_type": "tool_call_succeeded",
  "tool_name": "fetch_job_posts",
  "agent_name": "signal-researcher",
  "latency_ms": 1820,
  "payload": {
    "company_domain": "example.com",
    "window_days": 60,
    "output_ref": "jobs_ev_123"
  }
}
```

---

## 8. Subagent Logging Requirements

Every subagent run MUST log:

* parent trace_id
* subagent type
* task summary
* tool allowlist used
* start time
* end time
* cost
* token count
* transcript reference
* summary output reference
* success/failure

---

## 9. Compaction Logging Requirements

Compaction events MUST log:

* pre-compaction context estimate
* compaction trigger
* compacted summary reference
* fields persisted
* fields dropped
* linked KB refs
* post-compaction state checksum

This is required to debug memory-related regressions.

---

## 10. Evidence Logging Requirements

For every factual claim used in any outward-facing message or memo:

* claim_id MUST be created
* claim text MUST be stored
* evidence_refs MUST be linked
* originating trace_id MUST be recorded
* approving review_id MUST be recorded

### Claim Record Example

```json
{
  "claim_id": "claim_123",
  "claim_text": "Engineering hiring has accelerated in the last 60 days.",
  "lead_id": "lead_123",
  "approved": true,
  "review_id": "review_456",
  "evidence_refs": ["jobs_ev_123"],
  "trace_id": "trace_789"
}
```

---

## 11. Business Metrics to Derive from Logs

The observability layer MUST support calculation of:

* p50/p95 end-to-end latency
* p50/p95 tool latency
* cost per lead processed
* cost per qualified lead
* reply rate by outbound variant
* booking rate by segment
* stalled-thread rate
* review rejection rate
* human handoff rate
* false-claim block rate
* subagent usage frequency
* compaction frequency

---

## 12. Alerting Requirements

The system SHOULD support alerts for:

* repeated send failures
* CRM sync failures
* booking failure spikes
* tool error spikes
* cost overruns
* policy block spikes
* evidence-missing send attempts
* compaction failures

---

## 13. Acceptance Criteria

The observability subsystem is acceptable if:

* every lead run produces a trace
* every tool call is logged
* every send decision is explainable
* cost and latency can be computed per lead
* every claim in final outputs can be mapped to evidence

---