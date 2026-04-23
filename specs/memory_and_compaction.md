## 1. Purpose

This document defines how the system stores, retrieves, updates, and compacts memory across:

* persistent policy memory
* agent operating memory
* knowledge-base memory
* per-lead session memory
* compaction and rehydration flows

The memory subsystem exists to keep the system:

* grounded
* efficient
* auditable
* robust over long-running conversations

It MUST prevent context overload while preserving decision quality and traceability.

---

## 2. Goals

### M-1. Preserve important state

The system MUST retain all information required to continue work safely after:

* long conversations
* agent delegation
* compaction
* process restarts

### M-2. Separate durable knowledge from ephemeral scratchpad

The system MUST distinguish:

* long-lived knowledge
* reusable operating guidance
* per-lead mutable state
* temporary reasoning artifacts

### M-3. Maintain auditability

Compaction MUST NOT destroy:

* evidence references
* decision rationale
* policy flags
* external identifiers
* pending commitments

### M-4. Reduce active prompt pressure

Only decision-relevant context for the current step SHOULD remain in active context.

---

## 3. Memory Layers

## 3.1 Policy Memory

Policy memory contains stable operating constraints and is equivalent to system-wide instructions.

### Contents

* channel hierarchy rules
* no over-claiming rules
* no bench over-commitment rules
* public-data-only rule
* kill-switch behavior
* sink-routing behavior
* escalation conditions
* draft labeling requirements
* brand/tone hard rules

### Properties

* durable
* human-authored
* versioned
* loaded at session start
* referenced by all agents

### Storage

Recommended paths:

```text
memory/policy/global_policy.md
memory/policy/outbound_policy.md
memory/policy/bench_commitment_policy.md
memory/policy/escalation_policy.md
memory/policy/brand_voice_rules.md
```

---

## 3.2 Agent Operating Memory

This memory stores reusable agent-specific learnings and heuristics.

### Examples

* common false positives in AI maturity scoring
* typical ambiguity patterns in ICP classification
* scheduling timezone edge cases
* CRM field conventions
* tone-review heuristics for weak evidence

### Properties

* durable
* agent-scoped
* appendable
* versioned
* reviewed periodically

### Storage

```text
memory/agents/lead_orchestrator.md
memory/agents/signal_researcher.md
memory/agents/ai_maturity_scorer.md
memory/agents/icp_classifier.md
memory/agents/tone_and_claim_reviewer.md
memory/agents/scheduler.md
```

---

## 3.3 Knowledge Base Memory

This is the durable research layer and MUST be distinct from session context.

### Contents

* company pages
* signal briefs
* competitor gap briefs
* sector pages
* objection pages
* bench snapshots
* style guide extracts
* historical summaries
* cross-company comparisons

### Properties

* durable
* structured
* human-inspectable
* retrieval-oriented
* evidence-linked

### Storage

```text
kb/
├── companies/
├── signals/
├── gaps/
├── sectors/
├── objections/
├── bench/
├── playbooks/
├── style/
├── index.md
└── log.md
```

---

## 3.4 Lead Session Memory

This stores mutable state for a single lead and current conversation.

### Contents

* current lead stage
* latest known segment
* current AI maturity score
* confidence values
* outstanding questions
* open tasks
* pending sends
* pending bookings
* unresolved objections
* last customer intent
* linked KB pages
* external identifiers

### Properties

* mutable
* lead-scoped
* structured
* compactable
* rehydratable

### Storage

```text
state/leads/<lead_id>/session_state.json
state/leads/<lead_id>/conversation_state.json
state/leads/<lead_id>/pending_actions.json
```

---

## 3.5 Ephemeral Scratchpad

This is temporary working memory for the current run only.

### Contents

* partial tool results not yet persisted
* candidate hypotheses
* draft intermediate notes
* local reasoning artifacts
* temporary merge state across subagents

### Properties

* short-lived
* not authoritative
* safe to discard after persistence/compaction

### Rule

No business-critical information may exist only in ephemeral scratchpad.

---

## 4. Memory Write Rules

### M-5. Write to policy memory

Only humans or controlled administrative workflows MAY modify policy memory.

### M-6. Write to agent operating memory

Agents MAY append durable learnings only when:

* the learning is recurring
* it is not lead-specific
* it affects future behavior
* it is non-sensitive and verifiable

### M-7. Write to KB

Research-oriented agents SHOULD write to KB when:

* new company evidence has been synthesized
* a signal brief is finalized
* a competitor gap analysis is finalized
* a reusable objection or pattern has been identified

### M-8. Write to session state

The orchestrator MUST write session state after:

* stage transition
* inbound reply interpretation
* draft approval/rejection
* booking action
* escalation decision
* compaction event

---

## 5. Compaction

## 5.1 Purpose

Compaction reduces active context size while preserving operational continuity.

## 5.2 Trigger Conditions

Compaction SHOULD trigger when:

* token/context threshold is exceeded
* the conversation crosses a configurable turn count
* many tool results have accumulated
* subagent outputs have already been persisted
* a phase boundary is reached, such as:

  * enrichment complete
  * brief complete
  * outreach sent
  * reply handled
  * booking pending

## 5.3 Preconditions

Before compaction, the system MUST persist:

* current lead stage
* current next best action
* unresolved blockers
* pending sends/bookings
* linked brief IDs
* KB page references
* policy flags
* external IDs
* last interpreted prospect intent
* latest approved draft ID if relevant

## 5.4 What MUST be preserved

Compaction MUST preserve:

* lead_id
* company_id
* CRM record ID
* booking ID if any
* primary and alternate ICP segment
* AI maturity score and confidence
* unresolved objections
* pending action queue
* evidence packet IDs
* brief IDs
* policy block flags
* escalation flags
* last sent message IDs
* reply summary
* current stage

## 5.5 What MAY be compressed

The following MAY be summarized:

* long raw tool outputs
* repeated evidence excerpts
* verbose intermediate reasoning text
* superseded draft versions
* duplicate retrieval results

## 5.6 What MUST NOT be lost

The following MUST NOT be compacted into unverifiable prose only:

* source references
* confidence scores
* approved claims list
* unsupported claims list
* policy decisions
* timestamps of business events
* external system identifiers
* booked slot identifiers
* human handoff reasons

---

## 6. Compaction Output Schema

```json
{
  "lead_id": "string",
  "company_id": "string",
  "current_stage": "awaiting_reply",
  "primary_segment": "recently_funded_startup",
  "alternate_segment": "leadership_transition",
  "segment_confidence": 0.73,
  "ai_maturity_score": 2,
  "ai_maturity_confidence": 0.64,
  "current_objective": "await prospect response to first outreach",
  "last_customer_intent": "no_reply_yet",
  "confirmed_facts": [
    {
      "fact": "Raised Series A within 180 days",
      "evidence_ref": "ev_123"
    }
  ],
  "uncertain_facts": [
    {
      "fact": "Potential AI platform need inferred from hiring",
      "confidence": 0.41
    }
  ],
  "pending_actions": [
    {
      "action_type": "followup_email_if_no_reply",
      "scheduled_at": "timestamp"
    }
  ],
  "kb_refs": [
    "kb/signals/company_x.md",
    "kb/gaps/company_x.md"
  ],
  "brief_refs": [
    "brief_123",
    "gap_456"
  ],
  "crm_record_id": "crm_123",
  "policy_flags": [],
  "handoff_required": false,
  "next_best_action": "wait_or_followup",
  "compacted_at": "timestamp"
}
```

---

## 7. Rehydration

## 7.1 Purpose

Rehydration reconstructs working context after:

* compaction
* restart
* delayed reply
* manual intervention
* subagent return

## 7.2 Rehydration Inputs

The system MUST load:

* policy memory
* current lead session state
* current conversation state
* unresolved pending actions
* linked KB pages
* latest approved brief versions
* latest policy flags

## 7.3 Rehydration Output

The active context SHOULD contain only:

* concise lead summary
* current conversation stage
* unresolved issues
* next best action
* direct references to durable documents

---

## 8. Agent-Specific Memory Rules

### Lead Orchestrator

Uses:

* policy memory
* lead session state
* brief refs
* compact conversation summary

Must write:

* stage transitions
* decision summaries
* pending action updates

### Signal Researcher

Uses:

* company KB
* sector KB
* prior evidence summaries

Must write:

* evidence packet
* KB company updates
* source-linked research notes

### AI Maturity Scorer

Uses:

* scoring rubric
* prior scoring notes
* evidence packet

Must write:

* score record
* confidence rationale
* known uncertainty notes

### Reviewer

Uses:

* style rules
* claim-validation history
* policy memory

Must write:

* review result
* rejection reason or rewrite guidance

### Scheduler

Uses:

* timezone heuristics
* calendar policies
* lead schedule state

Must write:

* scheduling status
* timezone assumptions
* slot proposal history

---

## 9. Retention Rules

### Short-lived

* ephemeral scratchpad
* transient tool buffers
* superseded candidate reasoning

### Medium retention

* session states
* conversation summaries
* pending actions
* review histories

### Long-lived

* KB pages
* evidence packets
* final briefs
* policy decisions
* event traces
* booking outcomes

---

## 10. Acceptance Criteria

The memory subsystem is acceptable if:

* a lead can resume safely after compaction
* no policy-critical state is lost
* the same lead can be rehydrated across sessions
* agent contexts stay bounded
* KB and state are sufficient to reconstruct decisions

---