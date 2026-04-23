## 1. Purpose

This directory contains the complete system specification for the Tenacious lead generation and conversion engine.

It is intended to be the authoritative design reference for:

* engineering implementation
* agent behavior design
* tool and API contracts
* workflow orchestration
* memory and observability
* evaluation and acceptance

This spec set is written for a coding-agent-friendly workflow, where implementation can proceed from typed contracts, explicit workflows, and bounded agent responsibilities.

---

## 2. Reading Order

Recommended reading order for implementation teams:

1. `functional_requirements.md`
2. `non_functional_requirements.md`
3. `system_architecture.md`
4. `security_and_policy.md`
5. `state_machines.md`
6. `tool_registry.md`
7. `memory_and_compaction.md`
8. `observability_and_logging.md`
9. `agents/README.md`
10. `tools/README.md`
11. `workflows/README.md`
12. `api_contracts/README.md`
13. `schemas/README.md`
14. `domain_model.md`
15. `data_model.md`
16. `evaluation_and_acceptance.md`
17. `delivery_plan.md`

---

## 3. Directory Overview

### Top-level specs

These define system-wide behavior and constraints.

### `agents/`

Per-agent and per-subagent behavioral contracts.

### `tools/`

Tool group specifications and execution rules.

### `workflows/`

End-to-end process specifications across agents and services.

### `api_contracts/`

Typed contracts between runtime components.

### `schemas/`

Normalized payload definitions used across services.

### `appendices/`

Reference materials for traceability, assumptions, and glossary.

---

## 4. Spec Design Principles

All specs in this directory follow these principles:

* typed over implicit
* modular over monolithic
* evidence-backed over heuristic-only
* explicit workflows over hidden agent behavior
* policy-enforced side effects
* traceability for every business-critical action

---

## 5. Source of Truth Rules

* Functional behavior is governed by `functional_requirements.md`
* Runtime progression is governed by `state_machines.md`
* Safety behavior is governed by `security_and_policy.md`
* Tool access is governed by `tool_registry.md`
* Contract-level implementation is governed by `api_contracts/*` and `schemas/*`

If two specs conflict, precedence is:

1. `security_and_policy.md`
2. `state_machines.md`
3. `functional_requirements.md`
4. `api_contracts/*`
5. `schemas/*`
6. workflow and agent/tool specs

---

## 6. Intended Audience

* backend engineers
* orchestration/runtime engineers
* agent designers
* evaluators
* QA and policy reviewers
* future maintainers of the system

---

# `specs/agents/README.md`

## 1. Purpose

This directory defines the behavioral contracts for the system’s primary agent and subagents.

Each agent spec describes:

* mission
* responsibilities
* allowed tools
* required inputs and outputs
* memory usage
* constraints
* failure modes
* escalation conditions

---

## 2. Agent Model

The system follows a **central orchestrator + specialist subagent** pattern.

### Primary Agent

* `lead_orchestrator_spec.md`

### Specialist Subagents

* `signal_researcher_spec.md`
* `ai_maturity_scorer_spec.md`
* `competitor_gap_analyst_spec.md`
* `icp_classifier_spec.md`
* `tone_and_claim_reviewer_spec.md`
* `scheduler_spec.md`
* `crm_recorder_spec.md`
* `human_handoff_coordinator_spec.md`

---

## 3. Agent Design Rules

### A-1. Single clear responsibility

Each subagent MUST have a narrow, legible purpose.

### A-2. Constrained tool access

Each subagent MUST only access the tools explicitly granted to it.

### A-3. Structured outputs

Each subagent MUST return machine-usable outputs, not only freeform prose.

### A-4. Context isolation

Subagents SHOULD isolate noisy or domain-specific work from the main orchestrator context.

### A-5. No hidden authority

No subagent may perform a side effect outside its explicitly granted scope.

---

## 4. How to Use This Directory

Implementation teams should:

1. start with `lead_orchestrator_spec.md`
2. implement each subagent contract independently
3. enforce tool access from `tool_registry.md`
4. validate agent outputs using `schemas/*`
5. wire agent invocation paths from `workflows/*`

---

## 5. Implementation Notes

* Agent prompts should mirror these specs but not replace them
* Runtime validation should enforce state transitions and tool restrictions
* Agent memory should follow `memory_and_compaction.md`

---

# `specs/tools/README.md`

## 1. Purpose

This directory defines tool groups used by the orchestration runtime and agents.

The purpose of this directory is to make tools:

* modular
* typed
* safe
* testable
* separately implementable from agents

---

## 2. Tool Philosophy

Tools are the approved execution interface between the model layer and the rest of the system.

Agents MUST NOT directly call:

* raw vendor SDKs
* external APIs without wrappers
* internal services outside defined tool contracts

All side effects MUST occur through tools.

---

## 3. Tool Groups

This directory is split by tool domain:

* `evidence_tools_spec.md`
* `kb_tools_spec.md`
* `reasoning_tools_spec.md`
* `outreach_tools_spec.md`
* `crm_tools_spec.md`
* `scheduling_tools_spec.md`
* `policy_tools_spec.md`
* `observability_tools_spec.md`

These group specs supplement the master `tool_registry.md`.

---

## 4. Tool Design Rules

### T-1. Typed input/output

Every tool MUST use structured contracts.

### T-2. Narrow task boundary

A tool SHOULD do one thing well.

### T-3. Observable execution

Every tool call MUST be logged.

### T-4. Policy-aware side effects

Any tool that can send, book, write, or mutate state MUST enforce policy and idempotency.

### T-5. Evidence preservation

Evidence-returning tools MUST preserve source metadata.

---

## 5. Implementation Guidance

When implementing tools:

* start with pure read tools
* then implement write tools with idempotency
* then integrate observability and policy wrappers
* only then expose them to agents

---