## 1. Purpose

Defines when and how session, KB, and agent memory are written.

## 2. Trigger Examples

* after enrichment
* after score generation
* after review
* after reply interpretation
* after booking
* before compaction

## 3. Rules

* business-critical state must be written before it can be compacted away
* durable knowledge should go to KB, not ephemeral session state
* recurring heuristics may go to agent operating memory

---