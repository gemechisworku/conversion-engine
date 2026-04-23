## 1. Purpose

This workflow defines how a newly selected company becomes a fully researched lead with:

* normalized lead record
* evidence packet
* hiring signal brief
* AI maturity score
* competitor gap brief
* ICP classification
* CRM synchronization
* auditable trace

This is the system’s entry workflow for net-new leads.

---

## 2. Trigger Conditions

This workflow starts when:

* a new company is selected from the source dataset
* a manual operator submits a company for processing
* a retry is issued for an incomplete or failed enrichment

---

## 3. Preconditions

Before starting, the system MUST ensure:

* the company has a valid `company_id`
* source is allowed
* no conflicting active run exists for the same idempotency key
* kill switch state is known
* trace initialization is available

---

## 4. Inputs

```json
{
  "company_id": "string",
  "source": "crunchbase",
  "priority": "normal|high",
  "initiated_by": "system|human"
}
```

---

## 5. Outputs

Successful completion MUST produce:

* `lead_id`
* `evidence_packet_id`
* `brief_id`
* `score_id`
* `gap_brief_id`
* `classification_id`
* updated CRM record
* updated KB pages
* updated session state

---

## 6. Primary Actors

* Lead Orchestrator
* Signal Researcher
* AI Maturity Scorer
* Competitor Gap Analyst
* ICP Classifier
* CRM Recorder

---

## 7. Workflow Steps

### Step 1. Create or resolve lead record

The Lead Orchestrator MUST:

1. create or retrieve `lead_id`
2. initialize top-level trace
3. set lead state to `enriching`
4. write initial session state
5. emit `lead_created` or `session_resumed`

### Step 2. Run evidence collection

The Lead Orchestrator MUST delegate to `signal-researcher`.

The Signal Researcher MUST:

1. fetch company profile
2. fetch funding events
3. fetch job posts
4. fetch layoffs
5. fetch leadership changes
6. fetch tech stack
7. fetch other public AI signals
8. normalize evidence
9. persist evidence packet
10. update relevant KB pages

### Step 3. Generate hiring signal brief

The orchestrator MUST request brief synthesis from the research results.

The system MUST:

1. combine normalized signals
2. compute per-signal confidence
3. generate initial research hook
4. generate language guidance
5. attach evidence refs
6. write brief to KB and state

### Step 4. Score AI maturity

The orchestrator MUST delegate to `ai-maturity-scorer`.

The scorer MUST:

1. apply scoring rubric
2. assign score 0–3
3. assign confidence
4. attach justifications
5. persist result and refs

### Step 5. Generate competitor gap brief

The orchestrator MUST delegate to `competitor-gap-analyst`.

The analyst MUST:

1. identify sector/stage comparison set
2. compare AI maturity and public practices
3. estimate percentile
4. identify missing practices
5. add language/risk guidance
6. persist output

### Step 6. Run ICP classification

The orchestrator MUST delegate to `icp-classifier` or call classification flow.

The classifier MUST:

1. assign primary segment
2. assign alternate segment if relevant
3. produce confidence
4. abstain if needed
5. return rationale

### Step 7. Update lead state

On successful research completion, the orchestrator MUST:

1. set lead state to `brief_ready`
2. attach all brief/score/classification refs
3. update session and conversation state
4. append CRM record updates
5. emit `brief_generated`, `gap_brief_generated`, `classification_completed`

---

## 8. State Transitions

Allowed transitions:

* `new_lead -> enriching`
* `enriching -> brief_ready`
* `enriching -> disqualified`
* `enriching -> handoff_required`

---

## 9. Failure Handling

### F-1. Missing critical evidence

If critical evidence cannot be collected:

* workflow MAY continue with partial data
* system MUST downgrade confidence
* brief MUST include risk notes
* classification MAY abstain

### F-2. Contradictory signals

If signals materially conflict:

* system MUST record contradiction
* classifier SHOULD lower confidence or abstain
* orchestrator MAY require human review

### F-3. Adapter/tool failure

If one evidence source fails:

* retry according to retry policy
* record failure event
* continue with partial evidence if permissible

### F-4. Policy block

If policy prohibits continuation:

* set state to `handoff_required` or `disqualified`
* log policy decision

---

## 10. Acceptance Criteria

This workflow is acceptable if:

* a lead can be enriched end-to-end
* all outputs are persisted with IDs
* evidence refs exist for claimed signals
* confidence and risk notes are present
* state ends in `brief_ready` or valid fallback state

---
