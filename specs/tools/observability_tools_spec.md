## 1. Purpose

Defines tooling for logging events, spans, and claim/evidence relationships.

## 2. Tool Set

* `log_trace_event`
* `log_tool_use`
* `log_subagent_event`
* `log_compaction_event`
* `log_business_outcome`

## 3. Rules

* these tools must never block core business flow unless logging infrastructure failure is policy-critical
* best effort logging may be allowed, but trace creation should be strongly preferred
* business-critical outcomes should be durably recorded

---