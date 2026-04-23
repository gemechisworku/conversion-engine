This is the **deep reference for how specs are used**.


# IMPLEMENTATION PROTOCOL

## Purpose
Defines how specifications must be interpreted and translated into code.

This file is binding for all implementation.

---

## 1. Spec Roles

Each spec type has a defined role:

### Functional Requirements
Defines WHAT must be built.

### State Machines
Defines WHAT transitions are allowed.

### Workflows
Defines HOW the system operates step-by-step.

### Agent Specs
Defines WHO performs each responsibility.

### Tool Specs
Defines HOW external actions are executed.

### API Contracts
Defines HOW components communicate.

### Schemas
Defines DATA STRUCTURE.

### Policy
Defines WHAT is allowed or blocked.

---

## 2. Implementation Mapping

| Spec Type | Maps To Code |
|----------|-------------|
| workflows | LangGraph graphs |
| agents | node responsibilities |
| tools | service wrappers |
| api_contracts | service interfaces |
| schemas | Pydantic models |
| state_machines | validation + guards |
| policy | middleware / pre-checks |

---

## 3. Execution Pattern

All features MUST follow this pattern:

1. Load state
2. Validate state transition
3. Call service/tool
4. Apply policy checks
5. Persist results
6. Emit logs/traces

---

## 4. Service vs Agent Separation

### Services (deterministic)
- email sending
- SMS sending
- CRM writes
- booking
- enrichment

### Agents (LLM-driven)
- drafting
- classification
- reasoning
- response generation

Agents MUST NEVER:
- call providers directly
- perform side effects

---

## 5. LangGraph Rules

LangGraph is used for:
- orchestration
- routing
- state transitions

NOT for:
- provider logic
- scraping logic
- webhook parsing

Each node MUST:
- accept structured input
- call a service/tool
- return structured output

---

## 6. Error Handling Rules

All integrations MUST:

- return structured errors
- log failures
- avoid silent failure
- support retries where safe

Error types MUST align with:
`tool_registry.md`

---

## 7. Idempotency Rules

All write operations MUST be idempotent:

- email send → idempotency key
- SMS send → idempotency key
- CRM write → lead_id-based
- booking → lead_id + slot_id

---

## 8. Policy Enforcement Points

Policy MUST be checked BEFORE:

- sending email
- sending SMS
- booking meetings
- writing CRM updates

---

## 9. Webhook Processing Model

All webhook handlers MUST:

1. Validate payload
2. Normalize to internal schema
3. Classify event type
4. Route to downstream handler
5. Log event

They MUST NOT:
- contain business logic
- dead-end responses

---

## 10. Enrichment Rules

Enrichment pipeline MUST:

- implement all 4 sources
- avoid login/captcha bypass
- normalize outputs
- include per-signal confidence

---

## 11. CRM + Booking Linkage Rule

Booking MUST trigger CRM update:

````

Cal.com booking → HubSpot update

```

This MUST be implemented in a single callable flow.

---

## 12. Channel Hierarchy Rule

- Email = primary channel
- SMS = warm leads only

SMS MUST be gated via code logic, not documentation.

---

## 13. Completion Validation

Before marking a module complete:

- schemas match
- workflows satisfied
- state transitions valid
- policy enforced
- tests pass

---

## 14. Non-Negotiable Constraints

The system MUST NOT:

- fabricate data
- bypass policy
- create undefined states
- skip logging for critical actions
- send outbound messages without validation

---

## Final Principle

The system is:

Deterministic Core + Agent Orchestration

NOT:

Unstructured Agent Behavior
```

---