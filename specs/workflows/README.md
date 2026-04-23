## 1. Purpose

This directory contains the end-to-end workflow specifications that connect:

* agents
* tools
* APIs
* memory
* state transitions
* external systems

These workflows define **how the system operates**, not just what each component does independently.

---

## 2. Workflow Files

* `lead_intake_and_enrichment.md`
* `brief_generation.md`
* `icp_classification.md`
* `outreach_generation_and_review.md`
* `reply_handling.md`
* `scheduling_and_booking.md`
* `crm_sync.md`
* `memory_writeback.md`
* `context_compaction.md`
* `human_escalation.md`

Some workflows may initially be implemented as part of larger flows, but they are separated here for clarity and future modularization.

---

## 3. Workflow Rules

### W-1. State alignment

Every workflow MUST respect `state_machines.md`.

### W-2. Policy enforcement

Every workflow involving side effects MUST apply `security_and_policy.md`.

### W-3. Traceability

Every workflow MUST emit observable events.

### W-4. Persistence before loss

No workflow may rely on ephemeral context alone for business-critical state.

---

## 4. Recommended Implementation Order

1. `lead_intake_and_enrichment.md`
2. `outreach_generation_and_review.md`
3. `reply_handling.md`
4. `scheduling_and_booking.md`
5. `human_escalation.md`
6. memory and CRM-specific supporting flows

---