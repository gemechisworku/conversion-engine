This is the **entrypoint for any coding agent**.


# AGENTS.md

## Purpose
This file defines how a coding agent must interact with the codebase and specs.

The system is spec-driven. All implementation MUST follow the specifications under `/specs` and the execution plan under `/docs/implementation_plan.md`.

---

## 1. Mandatory Reading Order

Before implementing ANY feature, the agent MUST read in this order:

1. `/docs/implementation_plan.md`
2. `/specs/functional_requirements.md`
3. `/specs/security_and_policy.md`
4. `/specs/state_machines.md`
5. Relevant workflow in `/specs/workflows/`
6. Relevant agent/tool spec in `/specs/agents/` or `/specs/tools/`
7. Relevant API contract in `/specs/api_contracts/`
8. Relevant schema in `/specs/schemas/`

The agent MUST NOT skip steps.

---

## 2. Source of Truth Priority

If multiple specs conflict, resolve using this priority:

1. `security_and_policy.md` (highest priority)
2. `state_machines.md`
3. `functional_requirements.md`
4. `api_contracts/*`
5. `schemas/*`
6. `workflows/*`
7. `agents/*` and `tools/*`

If still unclear → STOP and log a spec gap.

---

## 3. Implementation Rules

The agent MUST:

- Only implement behavior defined in specs
- Use schemas as strict contracts (no extra/missing fields)
- Respect all state transitions in `state_machines.md`
- Enforce policy checks before:
  - sending messages
  - booking meetings
  - writing to CRM
- Use tools/services instead of embedding provider logic in agent nodes
- Keep LangGraph nodes thin (delegate to services)

The agent MUST NOT:

- invent new flows or states
- bypass policy checks
- hardcode behavior that belongs in specs
- couple provider logic directly into graphs

---

## 4. Webhook Constraint (IMPORTANT)

Webhook infrastructure is ALREADY deployed on Render.

The agent MUST:
- NOT implement a new webhook server
- Match existing deployed routes and payloads
- Focus on:
  - payload parsing
  - normalization
  - downstream routing
  - error handling

All webhook logic must be:
- deterministic
- testable with payload fixtures

---

## 5. Phase Execution Rule

The agent MUST follow `/docs/implementation_plan.md` phases in order:

### Current Active Phases (DO FIRST):
1. Phase 1: Email Handler
2. Phase 2: SMS Handler
3. Phase 3: HubSpot + Cal.com Integration
4. Phase 4: Signal Enrichment Pipeline

DO NOT jump to LangGraph orchestration until these are complete.

---

## 6. Completion Criteria (Strict)

A task is ONLY complete if:

- Code matches all relevant spec files
- API inputs/outputs match schemas
- Policy checks are enforced
- State transitions are valid
- Errors are handled explicitly (no silent failure)
- Logging/trace hooks exist where required
- Tests include:
  - success case
  - failure case
  - malformed input case

---

## 7. Spec Gap Protocol

If required behavior is NOT defined:

1. DO NOT guess
2. Add entry to:
   `/specs/appendices/open_questions.md`
3. Implement safest minimal version
4. Add comment:

```python
# SPEC-GAP: <description>
````

---

## 8. Traceability Rule

Each implementation MUST reference:

* Requirement (FR / NFR if applicable)
* Workflow file
* Schema file
* API contract

Example:

```python
# Implements: FR-8
# Workflow: outreach_generation_and_review.md
# Schema: outreach_draft.md
# API: outreach_api.md
```

---

## 9. Testing Requirements

For each integration (email, SMS, CRM, booking, enrichment):

Tests MUST include:

* valid payload
* invalid payload
* provider failure
* retry scenario
* routing verification

Webhook handlers MUST use real or fixture payloads.

---

## 10. Directory Responsibilities

The agent MUST follow this mapping:

* `services/` → provider integrations (email, SMS, CRM, calendar, enrichment)
* `tools/` → wrappers around services
* `nodes/` → LangGraph nodes (thin logic only)
* `graphs/` → orchestration
* `repositories/` → persistence
* `prompts/` → LLM instructions

---

## 11. Critical Rule

If unsure between:

* speed vs correctness → choose correctness
* guessing vs blocking → BLOCK and log spec gap

---

## Final Instruction

The agent MUST treat the system as:

SPEC → CONTRACT → CODE

NOT:

IDEA → CODE

````
