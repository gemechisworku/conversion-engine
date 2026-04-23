# Implementation Plan

## Purpose

This document is the implementation guide for the Tenacious conversion engine. It translates the spec set into a practical delivery sequence with a strong focus on the current milestone requirements:

1. Outbound email handler
2. SMS handler
3. HubSpot + Cal.com integration
4. Signal enrichment pipeline
5. Agent directory completeness using LangGraph

This plan is optimized for the current rubric and then extends into later phases for the full multi-agent system.

---

## Current priority

The immediate goal is not the full polished agent system. The immediate goal is to make the `agent/` directory implementation-ready and rubric-complete for:

* email sending and inbound reply handling
* SMS sending and inbound reply routing
* HubSpot MCP writes with enrichment fields
* Cal.com booking callable from agent code
* booking-to-HubSpot linkage
* enrichment from all required signal sources
* a clean callable interface that LangGraph nodes can attach to

The webhook server is already provisioned and running on Render, and the relevant provider accounts have already been wired to it. The implementation plan therefore assumes infrastructure-level webhook hosting and provider registration are complete, and shifts the current focus to:

* provider handler logic
* webhook payload validation and normalization
* downstream routing interfaces
* integration hardening
* observability, retries, and idempotency
* LangGraph node integration

The architecture should therefore be implemented in two layers:

### Layer A: Rubric-critical integration layer

Deterministic adapters, handlers, schemas, and service interfaces.

### Layer B: LangGraph orchestration layer

Graphs, nodes, state, and agent/subagent routing built on top of Layer A.

This sequencing reduces risk. It ensures the milestone passes even before the full orchestration graph is complete.

---

## Recommended implementation principles

### 1. Build handler-first, agent-second

Implement provider handlers and enrichment services as stable Python modules with clean interfaces. Then wrap them in LangGraph nodes.

### 2. Treat the rubric interfaces as product APIs

Even if they are internal modules, design them as if other parts of the system will depend on them.

### 3. Prefer deterministic code for integrations

Do not put sending, booking, CRM writing, or scraping logic inside prompt-heavy agent nodes. Keep those in services/tools.

### 4. Use LangGraph for orchestration, not basic plumbing

LangGraph should coordinate:

* which service runs next
* whether to delegate to a specialist node
* when to compact or persist state
* when to trigger escalation

It should not directly replace the email sender, webhook parser, or booking client.

### 5. Make inbound/outbound paths testable independently

Each handler must be runnable in isolation with fixtures and mocked webhooks.

---

## Suggested target project mapping

This plan assumes you already created the structure. The mapping below is the recommended implementation ownership inside `agent/`.

```text
agent/
├── requirements.txt
├── main.py
├── config/
│   ├── settings.py
│   └── logging.py
├── graphs/
│   ├── lead_graph.py
│   ├── reply_graph.py
│   ├── scheduling_graph.py
│   └── state.py
├── nodes/
│   ├── intake.py
│   ├── enrichment.py
│   ├── scoring.py
│   ├── classification.py
│   ├── outreach.py
│   ├── review.py
│   ├── reply_handling.py
│   ├── scheduling.py
│   ├── crm_sync.py
│   └── escalation.py
├── services/
│   ├── email/
│   │   ├── client.py
│   │   ├── webhook.py
│   │   ├── router.py
│   │   └── schemas.py
│   ├── sms/
│   │   ├── client.py
│   │   ├── webhook.py
│   │   ├── router.py
│   │   └── schemas.py
│   ├── crm/
│   │   ├── hubspot_mcp.py
│   │   └── schemas.py
│   ├── calendar/
│   │   ├── calcom_client.py
│   │   └── schemas.py
│   ├── enrichment/
│   │   ├── crunchbase.py
│   │   ├── jobs_playwright.py
│   │   ├── layoffs.py
│   │   ├── leadership.py
│   │   ├── merger.py
│   │   └── schemas.py
│   ├── policy/
│   │   ├── channel_policy.py
│   │   ├── bench_policy.py
│   │   └── escalation_policy.py
│   └── observability/
│       ├── langfuse_client.py
│       ├── events.py
│       └── decorators.py
├── prompts/
│   ├── orchestrator.md
│   ├── signal_researcher.md
│   ├── reviewer.md
│   ├── scheduler.md
│   └── classifier.md
├── repositories/
│   ├── lead_repo.py
│   ├── state_repo.py
│   ├── message_repo.py
│   └── kb_repo.py
├── tools/
│   ├── email_tools.py
│   ├── sms_tools.py
│   ├── crm_tools.py
│   ├── calendar_tools.py
│   ├── enrichment_tools.py
│   └── policy_tools.py
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

---

## Phase plan overview

### Phase 0. Foundation and runtime alignment

## Objectives

* align the local codebase with the already-running Render webhook server
* finalize Python environment and dependencies
* define shared config and secrets loading
* define common schemas and event/logging patterns
* define graph state objects
* verify webhook route contracts match the deployed server behavior

## Deliverables

* `agent/requirements.txt`
* environment configuration loader
* common logger
* base Pydantic models for shared payloads
* route contract alignment for deployed webhook endpoints
* LangGraph state classes

## Recommended tasks

### Task 0.1: requirements.txt

Include at minimum:

* langgraph
* langchain / langchain-openai or preferred provider SDK
* fastapi
* uvicorn
* pydantic
* httpx
* resend or mailersend SDK/client dependency
* africastalking
* playwright
* pandas
* python-dateutil
* langfuse
* python-dotenv
* tenacity
* pytest
* pytest-asyncio

### Task 0.2: shared settings

Implement `config/settings.py` with:

* RESEND_API_KEY or MAILERSEND_API_KEY
* AFRICASTALKING_USERNAME
* AFRICASTALKING_API_KEY
* HUBSPOT_MCP endpoint/config
* CALCOM_API_URL / token
* LANGFUSE keys
* webhook signing secrets if used
* RENDER webhook base URL
* CHALLENGE_MODE
* SINK_ROUTING_ENABLED
* KILL_SWITCH_ENABLED

### Task 0.3: common schemas

Create base schemas for:

* lead metadata
* inbound message
* outbound message request
* provider response
* booking result
* enrichment artifact
* error envelope

### Task 0.4: deployed webhook contract verification

Because the webhook server is already live on Render, verify and document:

* actual deployed routes
* expected provider payload shapes
* signature/header expectations
* retry semantics from providers
* local-to-deployed parity expectations

This is now more important than creating the server itself.

### Task 0.5: graph state

Define LangGraph state objects for:

* LeadGraphState
* ReplyGraphState
* SchedulingGraphState

Keep these minimal at first:

* lead_id
* company_id
* current_stage
* message context
* enrichment refs
* policy flags
* pending actions

## Exit criteria

* config loads cleanly
* deployed webhook contract is documented and matched in code
* graph state definitions compile
* dependencies install reproducibly

---

# Phase 1. Outbound email handler

## Why this is first

This is explicitly graded now and is one of the highest-value milestone components. It also becomes the base channel for the rest of the system.

## Rubric target

To reach mastered, the implementation must:

* use Resend or MailerSend
* receive inbound reply events via webhook
* expose a clear downstream interface
* handle failed sends, bounces, malformed payloads without silent failure

## Objectives

* implement provider-backed email sending
* implement inbound webhook parsing and validation
* expose a downstream routing interface
* create strong error handling and logging

## Deliverables

* `services/email/client.py`
* `services/email/webhook.py`
* `services/email/router.py`
* `services/email/schemas.py`
* tests for send success/failure and webhook parsing

## Recommended design

### Email service interface

Define a stable internal interface like:

```python
class EmailService:
    async def send_email(self, request: OutboundEmailRequest) -> ProviderSendResult: ...
    async def handle_webhook(self, payload: dict, headers: dict) -> InboundEmailEvent: ...
```

### Downstream interface requirement

This is critical for the rubric.

Implement one of these patterns:

* callback registration
* event emitter
* explicit handoff function

Recommended approach:

```python
class EmailEventRouter:
    async def route_inbound_reply(self, event: InboundEmailEvent) -> None: ...
    async def route_bounce(self, event: EmailBounceEvent) -> None: ...
```

Your webhook handler should parse provider payloads and route them into this downstream interface rather than dead-ending inside the route itself.

### Required outbound flow

1. validate outbound request
2. apply policy checks if appropriate
3. send via Resend or MailerSend
4. normalize provider response
5. emit log/trace event
6. return a stable result object

### Required inbound flow

1. receive webhook
2. validate signature if available
3. parse provider-specific payload
4. normalize to internal event model
5. branch by event type:

   * reply
   * bounce
   * delivery failure
   * malformed/unknown
6. route downstream
7. log result

## Implementation tasks

### Task 1.1: provider client

Implement Resend or MailerSend send wrapper.

Response should normalize:

* provider
* provider_message_id
* accepted
* raw_status
* error if any

### Task 1.2: webhook parser

Implement provider payload parsing and normalization against the already-deployed Render webhook contract.

Normalized inbound event should include:

* event_type
* provider_message_id
* from_email
* to_email
* subject
* text_body
* html_body if available
* received_at
* raw_payload_ref

The code should assume the HTTP endpoint exists already; your task here is to make the parsing, validation, normalization, and downstream routing logic production-safe.

### Task 1.3: bounce/error handling

Explicitly handle:

* send API failure
* bounce event
* malformed payload
* unknown event type

Do not silently discard. Return/log normalized error events.

### Task 1.4: downstream routing hook

Expose a downstream interface that the graph runtime can attach to.
Recommended pattern:

* `EmailEventRouter` with injected handler functions
* or an internal event bus abstraction

### Task 1.5: tests

Include tests for:

* successful send
* send failure
* valid reply webhook
* bounce webhook
* malformed payload
* router invocation
* parity with deployed webhook payload fixtures from the Render setup

## Exit criteria

* email can be sent through Resend or MailerSend
* reply webhook normalizes inbound reply
* bounce and malformed cases are handled visibly
* downstream interface exists and is callable
* handler behavior matches deployed webhook contract
* unit/integration tests pass

---

# Phase 2. SMS handler

## Why it is second

It is also directly rubric-scored and depends on channel policy. It should be implemented immediately after email because the warm-lead rule depends on prior email engagement logic.

## Rubric target

To reach mastered, the implementation must:

* use Africa's Talking
* support outbound and inbound
* enforce SMS as warm-lead only
* route inbound replies to downstream logic

## Objectives

* implement outbound SMS via Africa's Talking
* implement inbound SMS webhook handler
* enforce warm-lead gating clearly in code
* expose routed downstream handling

## Deliverables

* `services/sms/client.py`
* `services/sms/webhook.py`
* `services/sms/router.py`
* `services/sms/schemas.py`
* `services/policy/channel_policy.py`

## Recommended design

### Internal service interface

```python
class SMSService:
    async def send_warm_lead_sms(self, request: OutboundSMSRequest) -> ProviderSendResult: ...
    async def handle_inbound_sms(self, payload: dict, headers: dict) -> InboundSMSEvent: ...
```

The naming itself should encode channel hierarchy. Use function names such as:

* `send_warm_lead_sms`
* not `send_sms_to_prospect`

### Warm-lead gating

Implement a dedicated policy method:

```python
def can_use_sms(lead_state: LeadChannelState) -> PolicyDecision:
    ...
```

This should check for evidence of a prior email reply or explicit warm status.

### Required outbound flow

1. validate warm-lead eligibility
2. validate message payload
3. send via Africa's Talking
4. normalize response
5. log/trace

### Required inbound flow

1. receive webhook
2. parse Africa's Talking payload
3. normalize event
4. route to downstream handler
5. log/trace

## Implementation tasks

### Task 2.1: Africa's Talking client wrapper

Normalize outbound response:

* provider
* message_id if available
* recipient
* accepted
* status
* raw response

### Task 2.2: inbound webhook parser

Normalize inbound SMS event from the deployed Render webhook route:

* from_number
* to_number
* text
* received_at
* provider payload ref

As with email, the endpoint is already provisioned; the implementation focus is parser correctness, normalization, routing, and safe handling of malformed payloads.

### Task 2.3: explicit channel policy

Add code comments and policy checks showing SMS is not for cold outreach.
This should be visible in implementation, not just documentation.

### Task 2.4: downstream routing

Create `SMSRouter.route_inbound_message(...)` that hands off to reply handling logic.

### Task 2.5: tests

* outbound SMS allowed for warm lead
* outbound SMS blocked for cold lead
* inbound SMS parsed successfully
* inbound SMS routed downstream
* malformed SMS payload handled
* parity with deployed Africa's Talking webhook payload fixtures

## Exit criteria

* SMS sends through Africa's Talking
* inbound SMS webhook works
* routing exists
* warm-lead rule is enforced in code
* handler behavior matches deployed webhook contract
* tests pass

---

# Phase 3. HubSpot + Cal.com linked integration

## Why it is third

The rubric explicitly requires linkage, not just independent utilities. This is a common place teams lose points.

## Rubric target

To reach mastered, the implementation must:

* write HubSpot contact records through MCP
* include enrichment fields beyond basic contact info
* expose Cal.com booking from within the agent codebase
* trigger a HubSpot update after completed booking for the same prospect

## Objectives

* implement HubSpot MCP writer with enrichment schema
* implement callable Cal.com booking client
* link booking completion to CRM update

## Deliverables

* `services/crm/hubspot_mcp.py`
* `services/crm/schemas.py`
* `services/calendar/calcom_client.py`
* `services/calendar/schemas.py`
* linked booking-to-CRM update flow

## Recommended design

### HubSpot service interface

```python
class HubSpotService:
    async def upsert_contact(self, contact: CRMLeadPayload) -> CRMWriteResult: ...
    async def append_enrichment(self, lead_id: str, enrichment: CRMEnrichmentPayload) -> CRMWriteResult: ...
    async def record_booking(self, lead_id: str, booking: CRMBookingPayload) -> CRMWriteResult: ...
```

### Required enrichment fields

Your HubSpot write should include at least:

* company / domain
* ICP segment classification
* alternate segment if available
* segment confidence
* AI maturity score
* enrichment timestamp
* funding signal summary
* job velocity summary
* layoffs signal summary
* leadership signal summary
* bench match status if available
* brief references or IDs if supported

### Cal.com service interface

```python
class CalComService:
    async def get_available_slots(...): ...
    async def book_discovery_call(request: BookingRequest) -> BookingResult: ...
```

### Critical linkage rule

This is required for mastered.

When `book_discovery_call(...)` succeeds, the calling flow must immediately trigger a HubSpot write for the same lead/prospect.

Recommended orchestration pattern:

1. book via Cal.com
2. normalize booking result
3. call `hubspot_service.record_booking(...)`
4. log both operations under same trace

Do not leave Cal.com as a standalone utility script.

## Implementation tasks

### Task 3.1: HubSpot MCP wrapper

Implement create/update behavior with a normalized interface.

### Task 3.2: enrichment payload mapping

Create a mapper that transforms internal enrichment artifact into CRM fields.

### Task 3.3: Cal.com booking wrapper

Implement:

* availability lookup
* booking call
* normalized response with booking_id / confirmation URL / start-end time

### Task 3.4: linked booking sync

Add a dedicated function such as:

```python
async def book_and_sync_crm(lead_id: str, booking_request: BookingRequest) -> LinkedBookingResult:
    ...
```

This should be callable from LangGraph scheduling nodes.

### Task 3.5: tests

* HubSpot write includes enrichment fields
* Cal.com booking returns normalized object
* successful booking triggers HubSpot update
* booking failure does not falsely update CRM

## Exit criteria

* HubSpot writes enrichment fields
* Cal.com booking is callable from codebase
* booking success triggers HubSpot update for same lead
* tests pass

---

# Phase 4. Signal enrichment pipeline

## Why it is fourth

It is rubric-critical and also foundational for downstream agent reasoning. Implement it before heavy LangGraph decision-making.

## Rubric target

To reach mastered, the implementation must:

* implement all four sources
* use Playwright without login or captcha bypass
* merge outputs into a structured artifact with per-signal confidence scores

## Objectives

* implement the four required signal collectors
* normalize outputs into a shared schema
* merge them into one enrichment artifact
* include per-signal confidence scores

## Deliverables

* `services/enrichment/crunchbase.py`
* `services/enrichment/jobs_playwright.py`
* `services/enrichment/layoffs.py`
* `services/enrichment/leadership.py`
* `services/enrichment/merger.py`
* `services/enrichment/schemas.py`

## Required sources

### Source 1: Crunchbase ODM lookup

Implement deterministic lookup from provided/frozen data source.
Output should include:

* company identifiers
* firmographics
* funding info
* industry/location metadata

### Source 2: Job posts via Playwright

Implement job-post scraping from public careers/job pages.
Must:

* use public pages only
* contain no login logic
* contain no captcha bypass
* contain no stealth or session abuse logic

Output should include:

* engineering role count
* AI-adjacent role count
* extracted role titles
* scrape timestamp
* source URLs
* velocity inputs if historical snapshot available

### Source 3: layoffs.fyi parsing

Implement CSV parsing and company matching.
Output should include:

* layoff date
* affected count/percent if available
* matched confidence
* source ref

### Source 4: leadership change detection

Implement detection via:

* Crunchbase fields if available
* public press/blog pages
* company news or similar public signals

Output should include:

* role name
* person if public and permitted
* change type
* date if inferred/found
* confidence
* source refs

## Enrichment artifact schema

The merged artifact should look like:

```json
{
  "company_id": "...",
  "generated_at": "...",
  "signals": {
    "crunchbase": {
      "summary": {},
      "confidence": 0.95,
      "source_refs": []
    },
    "job_posts": {
      "summary": {},
      "confidence": 0.78,
      "source_refs": []
    },
    "layoffs": {
      "summary": {},
      "confidence": 0.88,
      "source_refs": []
    },
    "leadership_changes": {
      "summary": {},
      "confidence": 0.63,
      "source_refs": []
    }
  },
  "merged_confidence": {
    "funding_signal": 0.95,
    "hiring_signal": 0.78,
    "layoff_signal": 0.88,
    "leadership_signal": 0.63
  }
}
```

The rubric specifically cares that confidence scores exist per signal in schema.

## Implementation tasks

### Task 4.1: source adapters

Implement each source collector independently.

### Task 4.2: compliance review for Playwright

Before considering done, verify the scraper contains:

* no login selectors
* no credential use
* no captcha solving logic
* no bypass scripts

### Task 4.3: merger

Implement deterministic merge logic that combines the four sources.

### Task 4.4: confidence assignment

Start with simple explicit confidence heuristics. Do not overcomplicate.
Examples:

* direct structured dataset match: high
* weak fuzzy match: medium/low
* inferred leadership change from press snippet: medium

### Task 4.5: tests

* each source adapter returns normalized output
* merger produces complete schema
* missing one source still yields partial artifact with explicit lower confidence
* Playwright module contains no login flow

## Exit criteria

* all four source adapters implemented
* Playwright is compliant
* merged structured artifact exists
* per-signal confidence scores present
* tests pass

---

# Phase 5. LangGraph orchestration layer

## Why this comes after integrations

You prefer LangGraph, and that is the right choice for the agent layer. But the graph should sit on top of stable service modules.

## Objectives

* wire deterministic services into graph nodes
* define state transitions and conditional routing
* support subgraph-like delegation patterns
* keep rubric-critical handlers callable independently

## Deliverables

* `graphs/lead_graph.py`
* `graphs/reply_graph.py`
* `graphs/scheduling_graph.py`
* node modules in `nodes/`
* graph state schemas

## Recommended graph structure

### Graph 1: Lead intake graph

Flow:

1. initialize lead
2. enrichment node
3. score/classify node
4. CRM sync node
5. outreach draft node
6. review node
7. send email node

### Graph 2: Reply handling graph

Flow:

1. normalize inbound message
2. load lead state
3. intent/reply analysis node
4. route to:

   * clarification
   * objection handling
   * scheduling
   * escalation

### Graph 3: Scheduling graph

Flow:

1. validate warm lead
2. resolve timezone
3. get slots
4. propose or confirm
5. book via Cal.com
6. sync HubSpot

## Recommended node design

Each node should be thin and call a service layer.
Example:

* `enrichment_node` calls `EnrichmentPipeline.run(...)`
* `send_email_node` calls `EmailService.send_email(...)`
* `booking_node` calls `CalComService.book_discovery_call(...)` then `HubSpotService.record_booking(...)`

This makes nodes easier to test and swap.

## Subagent pattern in LangGraph

Implement specialist tasks as dedicated nodes or subgraphs, not as unbounded freeform agents at first.
Prioritize:

* signal research node/subgraph
* classification node
* reviewer node
* scheduling node

You can later add fully agentic variants when the deterministic baseline is stable.

## Exit criteria

* lead graph can process new lead to first email send
* reply graph can process inbound email event
* scheduling graph can perform book-and-sync flow
* graphs rely on service interfaces, not direct provider code

---

# Phase 6. Review, logging, and resilience hardening

## Objectives

* implement robust logging and trace linkage
* make errors visible and non-silent
* add retries and idempotency
* improve test coverage for webhook and integration paths

## Deliverables

* Langfuse integration
* event logging wrappers
* normalized error types
* retry decorators
* idempotency keys for send/book/CRM writes

## High-priority tasks

* add trace_id propagation through all handlers
* log malformed webhooks explicitly
* ensure bounce events create structured records
* add provider timeout handling
* add integration tests with mocks and fixture payloads

## Exit criteria

* every critical provider interaction logged
* retries bounded and safe
* silent failure paths eliminated

---

# Phase 7. Full challenge extension

Once the current milestone is secured, expand toward the full challenge system.

## Additions

* competitor gap analyst implementation
  n- AI maturity scoring specialist
* tone-and-claim reviewer model node
* memory and compaction
* evidence graph generation
* probe library harness
* benchmark export helpers
* memo data pipeline

This phase is important, but it should not delay the rubric-critical implementation above.

---

# Recommended implementation order by file group

## Week / sprint order

### Block 1: foundation

* requirements.txt
* settings.py
* schemas
* logger
* deployed webhook contract verification

### Block 2: email

* email client
* email webhook parser
* email router
* deployed payload fixture tests
* tests

### Block 3: SMS

* Africa's Talking client
* SMS webhook parser
* channel policy
* SMS router
* tests

### Block 4: CRM + calendar

* HubSpot MCP wrapper
* Cal.com wrapper
* linked booking sync
* tests

### Block 5: enrichment

* Crunchbase adapter
* layoffs parser
* Playwright jobs scraper
* leadership detector
* merger and schema
* tests

### Block 6: LangGraph

* state definitions
* lead graph
* reply graph
* scheduling graph
* node wiring

### Block 7: hardening

* Langfuse traces
* retries
* idempotency
* failure-path tests

---

# Definition of done for the current stage

The current stage should be considered complete when all of the following are true:

## Email handler

* Resend or MailerSend used for sending
* inbound reply webhook implemented
* downstream interface exposed
* bounces, failed sends, malformed payloads handled visibly

## SMS handler

* Africa's Talking used for outbound
* inbound SMS implemented
* SMS gated to warm leads in code
* inbound routed downstream

## CRM + Calendar

* HubSpot MCP writes enrichment fields beyond basic contact info
* Cal.com booking callable in codebase
* successful booking triggers matching HubSpot update

## Enrichment pipeline

* Crunchbase implemented
* Playwright jobs scraper implemented with no login or captcha bypass
* layoffs.fyi parsing implemented
* leadership change detection implemented
* outputs merged into structured artifact with per-signal confidence

## Graph integration

* at least one LangGraph flow can call the above services end-to-end

---

# Risks and mitigations

## Risk 1: Overbuilding agent logic too early

Mitigation:

* finish deterministic services first
* keep graph nodes thin

## Risk 2: Losing points on linkage details

Mitigation:

* explicitly implement booking -> HubSpot sync in one callable function
* explicitly implement inbound routing interfaces for email and SMS

## Risk 3: Silent failures in webhooks

Mitigation:

* normalized error envelopes
* explicit malformed payload logging
* provider payload fixtures in tests

## Risk 4: SMS warm-lead rule only documented, not enforced

Mitigation:

* add dedicated `can_use_sms(...)` policy code
* make outbound SMS function naming reflect policy intent

## Risk 5: Playwright scraper accidentally includes disallowed behavior

Mitigation:

* keep scraper minimal and public-page-only
* no credentials, no session logic, no captcha code
* add code review checklist for scraper compliance

---

# Suggested immediate next tasks

If implementation starts now, the recommended first 10 tasks are:

1. Finalize `requirements.txt`
2. Create shared settings and secrets loader
3. Document the deployed Render webhook routes, headers, and payload contracts
4. Implement `services/email/schemas.py`
5. Implement Resend or MailerSend client wrapper
6. Implement email webhook parser and router interface against deployed payloads
7. Add email send + webhook parity tests
8. Implement Africa's Talking SMS wrapper and inbound parser
9. Add `can_use_sms(...)` warm-lead policy
10. Implement HubSpot MCP wrapper with enrichment payload mapping

After that:
11. Implement Cal.com booking wrapper
12. Implement `book_and_sync_crm(...)`
13. Build Crunchbase adapter
14. Build layoffs parser
15. Build Playwright jobs scraper
16. Build leadership detector
17. Build enrichment merger
18. Create lead graph in LangGraph
19. Create reply graph
20. Add observability and retry hardening

---

# Final recommendation

For this milestone, optimize for **rubric-complete infrastructure with LangGraph-compatible interfaces**.

Because the webhook server is already live on Render and connected to the required provider accounts, the implementation focus should now move away from server setup and toward:

* handler correctness
* payload normalization
* downstream routing
* integration linkage
* observability
* idempotency and failure handling

That means:

* provider handlers first
* linked CRM/calendar flow second
* enrichment pipeline third
* LangGraph orchestration on top

