## 1. Purpose

This document defines the recommended implementation sequence for the system.

The goal is to build in a safe order:

* state and contracts first
* read-only research second
* outbound actions later
* scheduling and escalation after stable core flows

---

## 2. Implementation Phases

## Phase 0. Foundation

Build:

* schemas
* state machine enforcement
* trace/event plumbing
* policy framework
* KB structure
* basic operational stores

Deliverables:

* schema validation
* state transition validation
* trace creation
* memory write/read primitives

---

## Phase 1. Research Core

Build:

* evidence adapters
* enrichment workflow
* signal brief generation
* AI maturity scoring
* ICP classification

Deliverables:

* lead intake to `brief_ready`
* KB updates
* evidence refs
* confidence-aware research output

---

## Phase 2. Outreach Core

Build:

* draft generation
* review pipeline
* policy checks
* send queue abstractions
* CRM writebacks

Deliverables:

* first-touch email end-to-end
* reviewed and logged outbound flow

---

## Phase 3. Reply Handling

Build:

* inbound ingestion
* intent interpretation
* conversation state updates
* objection handling paths
* follow-up generation

Deliverables:

* reply-to-response loop
* qualification state progression

---

## Phase 4. Scheduling

Build:

* timezone handling
* slot lookup
* proposal flow
* booking confirmation
* CRM booking sync

Deliverables:

* scheduling end-to-end

---

## Phase 5. Handoff and Hardening

Build:

* escalation packaging
* retry and recovery logic
* compaction/rehydration hardening
* metrics dashboards
* benchmark export helpers

Deliverables:

* safe fallback and evaluation readiness

---

## 3. Milestone Map

### Milestone A

`new_lead -> brief_ready`

### Milestone B

`brief_ready -> awaiting_reply`

### Milestone C

`awaiting_reply -> qualifying|scheduling`

### Milestone D

`scheduling -> booked`

### Milestone E

Full observability + evidence graph + compaction continuity

---

## 4. Implementation Dependencies

* workflows depend on schemas + state machines
* agents depend on tools + policy + memory
* sends depend on reviewer + policy + observability
* booking depends on stable conversation state
* evaluation depends on full event completeness

---

## 5. Recommended Team Split

If multiple engineers are involved:

### Stream 1

Contracts + schemas + storage

### Stream 2

Research tools + KB + enrichment

### Stream 3

Agent orchestration + review + memory

### Stream 4

Integrations + CRM + scheduling + delivery

### Stream 5

Observability + evaluation + reporting

---
