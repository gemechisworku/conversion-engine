## 1. Purpose

Defines policy enforcement tools.

## 2. Tool Set

* `check_kill_switch`
* `check_sink_routing`
* `check_bench_commitment`
* `require_human_handoff`
* `redact_sensitive_content`

## 3. Rules

* policy tools are authoritative for allow/block/escalate decisions
* failures and blocks must be logged as policy decisions
* policy tools should be callable by orchestrator/reviewer and guarded services

---