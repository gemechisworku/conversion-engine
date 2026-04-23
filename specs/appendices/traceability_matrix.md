## 1. Purpose

Maps requirements to implementation artifacts and validation.

## 2. Example Structure

| Requirement ID | Spec File                      | Workflow/API/Schema                                                | Test/Evidence               |
| -------------- | ------------------------------ | ------------------------------------------------------------------ | --------------------------- |
| FR-2           | functional_requirements.md     | research_api.md, hiring_signal_brief.md                            | enrichment integration test |
| FR-8           | functional_requirements.md     | outreach_generation_and_review.md, tone_and_claim_reviewer_spec.md | draft rejection test        |
| FR-14          | functional_requirements.md     | memory_and_compaction.md, session_state.md                         | compaction/rehydration test |
| NFR-22         | non_functional_requirements.md | observability_and_logging.md, observability_api.md                 | trace completeness check    |
| P-2            | security_and_policy.md         | policy tools, reviewer, handoff workflow                           | blocked commitment test     |

---