# Implementation checklist vs `implementation_plan.md`

This table maps the plan to concrete locations and status. **Done** = matches rubric intent; **Partial** = exists but not full scope; **Missing** = not started or not in repo.

| Plan section | Task / deliverable | Key location(s) | Status |
|--------------|-------------------|-----------------|--------|
| **Phase 0** | Requirements | `agent/requirements.txt` | Done |
| **Phase 0** | Settings / secrets | `agent/config/settings.py` | Done |
| **Phase 0** | Logging | `agent/config/logging.py` | Done |
| **Phase 0** | Graph state objects | `agent/graphs/state.py` | Done |
| **Phase 0** | Webhook contract verification | `specs/`, deploy docs | Partial — confirm vs Render |
| **Phase 1** | Email client / webhook / router | `agent/services/email/` | Done |
| **Phase 1** | Email tests | `agent/tests/unit/test_email_*.py` | Done |
| **Phase 2** | SMS + warm policy | `agent/services/sms/`, `policy/channel_policy.py` | Done |
| **Phase 2** | SMS tests | `agent/tests/unit/test_sms_*.py` | Done |
| **Phase 3** | HubSpot MCP | `agent/services/crm/hubspot_mcp.py` | Done |
| **Phase 3** | Cal.com + **book_and_sync_crm** | `agent/services/calendar/calcom_client.py` | Done |
| **Phase 3** | CRM enrichment mapping | `map_enrichment_to_crm_payload` in hubspot_mcp | Done |
| **Phase 3** | Linked booking tests | `agent/tests/unit/test_crm_calendar_integration.py` | Done |
| **Phase 4** | Four signal sources + merger | `agent/services/enrichment/` | Done |
| **Phase 4** | Playwright compliance (no login) | `jobs_playwright.py` | Done — re-verify on change |
| **Phase 4** | Act II / CFPB / news research | `act2_pipeline.py`, `web_research/` | Done (extensions) |
| **Phase 5** | **LangGraph** lead intake (enrich → CRM) | `agent/graphs/lead_intake_langgraph.py` | **Done** (this iteration) |
| **Phase 5** | **LangGraph** scheduling (book → transition) | `agent/graphs/scheduling_langgraph.py` | **Done** (this iteration) |
| **Phase 5** | Lead graph: draft → review → send | — | Missing |
| **Phase 5** | Reply graph: branch clarify / objection / schedule / escalate | `reply_graph.py` (thin) | Partial |
| **Phase 5** | Full `nodes/` matrix (intake, outreach, crm_sync, …) | `agent/nodes/` | Partial (3 modules) |
| **Phase 5** | `prompts/` | — | Missing |
| **Phase 6** | Langfuse traces | Settings only; `observability/events.py` | Partial |
| **Phase 6** | **Pipeline / graph progress logs** | `log_processing_step` in `observability/events.py`; used by `runtime.py`, `lead_intake_langgraph.py`, `scheduling_langgraph.py`, `web_research/runner.py` | **Done** (stdout via stdlib logging) |
| **Phase 6** | Retries / idempotency everywhere | HubSpot calls use keys | Partial |
| **Phase 6** | Integration tests (fixtures) | Some CRM/calendar | Partial |
| **Phase 7** | Competitor gap / AI maturity | `competitor_gap.py`, `ai_maturity.py` | Done |
| **Phase 7** | Reviewer node, memory, evidence graph | — | Missing |

## What was added in the latest iteration

- **`lead_intake_langgraph`**: LangGraph `StateGraph` with nodes `enrich` → `crm_sync` (HubSpot optional), invoked from `OrchestrationRuntime.process_lead`.
- **`scheduling_langgraph`**: LangGraph with nodes `book_and_sync` → `transition`, invoked from `run_scheduling`.

## Suggested next steps (not implemented here)

1. LangGraph nodes for **outreach draft → review → send** and wire `advance_state` or a new graph runner.
2. Expand **reply** routing into conditional LangGraph edges.
3. **Langfuse** SDK wrapper + trace propagation.
4. **`prompts/`** and reviewer specialist per plan.

## Test commands and guide

### 1) Unit tests (from repo `agent/` directory)

```powershell
Set-Location "d:\FDE-Training\week-10\conversion-engine\agent"
python -m pytest tests/unit/test_lead_intake_langgraph.py tests/unit/test_scheduling_langgraph.py tests/unit/test_orchestration_runtime.py -v --tb=short
```

**Expected:** All selected tests **passed** (green). Failures usually mean import/cycle issues or mock drift.

Run the full agent unit suite:

```powershell
python -m pytest tests/unit/ -q --tb=line
```

**Expected:** **71** tests passed when run from `agent/` (all `tests/unit/`).

### 2) Act II live smoke (optional, needs env)

From repo root:

```powershell
Set-Location "d:\FDE-Training\week-10\conversion-engine"
.\scripts\smoke-act2-live.ps1 `
  -ProspectEmail "you@example.com" `
  -SmsTo "+15551234567" `
  -CompanyId "your-company-id" `
  -CompanyName "Your Company" `
  -CompanyDomain "yourdomain.com" `
  -SkipSms `
  -SkipBooking `
  -SkipUnitTests
```

**Expected:** `outputs/evidence/act2_live_<timestamp>/02_orchestration_stdout.json` shows JSON with `lead_id`, `state`, `act2_artifact_paths`; under `lead_<id>/` you see `enrichment_brief.json`, `news_brief.json`, etc.

### 3) Quick sanity: import graphs

```powershell
Set-Location "d:\FDE-Training\week-10\conversion-engine\agent"
python -c "from agent.graphs.lead_intake_langgraph import compile_lead_intake_graph, LeadIntakeGraphDeps; print('ok', compile_lead_intake_graph)"
```

**Expected:** prints `ok` and a compiled graph class name without `ImportError`.

### 4) See pipeline logs during a run

Logging uses the root format from `agent/config/logging.py` (timestamp, level, logger name, message). **Logger names** include `agent.orchestration`, `agent.graphs.lead_intake`, `agent.graphs.scheduling`, `agent.graphs.web_research`.

```powershell
$env:LOG_LEVEL = "INFO"
Set-Location "d:\FDE-Training\week-10\conversion-engine\agent"
python -m pytest tests/unit/test_orchestration_runtime.py::test_process_lead_generates_brief_ready_state -v -s 2>&1 | Select-String "agent\."
```

**Expected:** Lines containing `[process_lead.start]`, `[graph]`, `[enrich.start]`, `[enrich.done]`, `[crm_sync.skip]` or `[crm_sync.*]`, and `[process_lead.graph_done]` when HubSpot is absent (unit test uses `hubspot_service=None`).

---

## Architecture note

- **Service layer** remains the source of truth (`run_lead_intake`, `book_and_sync_crm`, HubSpot MCP).
- **LangGraph** sequences those calls with explicit state for observability and future conditional edges (plan Phase 5).
