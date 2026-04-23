# Tenacious AI Lead Engine

## Overview

This system is an AI-powered lead generation, enrichment, and conversion engine designed to identify high-quality prospects, generate research-backed outreach, and guide them through qualification and booking workflows.

At its core, the system combines:

* **AI agents (LangGraph-based orchestration)**
* **Deterministic service integrations (email, SMS, CRM, calendar)**
* **Structured enrichment pipelines**
* **Policy and safety enforcement layers**

The goal is to move from **raw company data -> qualified conversation -> booked meeting**, while ensuring all actions are traceable, policy-compliant, and evidence-backed.

---

## What the System Does

### 1. Lead Intake & Enrichment

The system ingests a company and enriches it using multiple public data sources:

* Crunchbase (firmographics, funding)
* Job postings (via Playwright scraping)
* layoffs.fyi (layoff signals)
* Leadership change detection (public signals)

These signals are merged into a **structured enrichment artifact** with confidence scores.

---

### 2. Signal Interpretation & Classification

Using the enrichment data, the system:

* Identifies hiring and timing signals
* Assigns an **ICP (Ideal Customer Profile) segment**
* Estimates **AI maturity level**
* Produces a **research brief** for outreach

---

### 3. Outreach Generation

The system generates outbound messages that are:

* grounded in real signals
* aligned with prospect context
* adapted to confidence levels

Messages go through:

* drafting
* review (tone + claims)
* policy validation

before being sent.

---

### 4. Communication Channels

#### Email (Primary Channel)

* Sent via **Resend**
* Inbound replies received via webhook
* Replies normalized and routed into the system

#### SMS (Secondary Channel)

* Sent via **Africa's Talking**
* Only used for **warm leads** (never cold outreach)
* Supports bidirectional communication

---

### 5. CRM Integration

The system integrates with **HubSpot (via MCP)** to:

* store enriched lead records
* attach classification and signal data
* track communication and lifecycle state

---

### 6. Scheduling & Booking

The system integrates with **Cal.com** to:

* propose meeting slots
* confirm bookings

When a booking is completed, a matching **HubSpot update is triggered automatically**.

---

### 7. Reply Handling & Conversation Flow

Inbound messages are:

* parsed and normalized
* classified into intent (interest, objection, scheduling, etc.)
* routed to the correct next step

The system maintains **conversation state** to guide follow-ups.

---

### 8. Human Escalation

When the system encounters:

* pricing requests
* legal/compliance questions
* insufficient evidence

it generates a **handoff package** for a human operator.

---

## Architecture Summary

The system follows a layered architecture:

1. **Service Layer**: deterministic provider integrations.
2. **Tool Layer**: wrappers around services.
3. **Agent Layer (LangGraph)**: orchestration and routing.
4. **Workflow Layer**: end-to-end operational paths.
5. **Policy Layer**: safety and authority checks.
6. **Memory & State Layer**: lead/conversation/session continuity.
7. **Observability Layer**: traces, events, and outcomes.

Agents do not call providers directly; they call tools/services.

---

## Tech Stack

* **LangGraph** -> orchestration
* **FastAPI (Render)** -> webhook hosting
* **Resend** -> email
* **Africa's Talking** -> SMS
* **HubSpot MCP** -> CRM
* **Cal.com** -> scheduling
* **Playwright** -> job post scraping
* **Langfuse** -> observability
* **Pydantic** -> contracts/schemas

---

## How Everything Connects

```text
Company -> Enrichment -> Classification -> Brief
        -> Outreach -> Email -> Reply -> Scheduling -> Booking
                                              |
                                         HubSpot Update
```

---

## Current Implementation Focus

The active milestone focus is:

* Email handler (send + inbound webhook)
* SMS handler (with warm-lead gating)
* HubSpot integration with enrichment fields
* Cal.com booking with CRM linkage
* Signal enrichment pipeline (4 sources)

---

## Environment Variables and Credentials

1. Copy `.env.example` to `.env`.
2. Fill all fields required for your environment.

```bash
cp .env.example .env
```

### Where to get each credential

* `RESEND_API_KEY`: Resend dashboard -> API Keys.
* `RESEND_FROM_EMAIL`: verified sender identity in Resend dashboard -> Domains / Senders.
* `RESEND_WEBHOOK_SECRET`: Resend dashboard -> Webhooks -> your endpoint signing secret.
* `AFRICASTALKING_USERNAME`, `AFRICASTALKING_API_KEY`: Africa's Talking dashboard -> Settings -> API Key.
* `AFRICASTALKING_SHORTCODE`: sender ID/shortcode configured in Africa's Talking.
* `AFRICASTALKING_API_URL`: keep default unless Africa's Talking provides a different regional endpoint.
* `HUBSPOT_MCP_BASE_URL`, `HUBSPOT_MCP_API_KEY`: your deployed HubSpot MCP URL and auth token.
* `CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`: Cal.com -> Developers -> API keys and event type.
* `CALCOM_WEBHOOK_SECRET`: Cal.com webhook settings.
* `CRUNCHBASE_DATASET_PATH` / `CRUNCHBASE_DATASET_URL`: path or URL for your Crunchbase snapshot used by enrichment.
* `LAYOFFS_CSV_PATH` / `LAYOFFS_CSV_URL`: layoffs.fyi CSV source used by the layoffs adapter.
* `LEADERSHIP_FEED_URL`: JSON feed or local JSON file path for leadership-change detection.
* `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`: Langfuse project settings -> API keys.
* `RENDER_WEBHOOK_BASE_URL`: base URL of your deployed webhook server on Render.
* `WEBHOOK_ROUTE_RESEND`, `WEBHOOK_ROUTE_AFRICASTALKING`, `WEBHOOK_ROUTE_CALCOM`: deployed path values.

Notes:

* Keep `.env` out of version control.
* Use payload fixtures from your deployed webhooks for parser parity tests.

---

## Getting Started

1. Read `/docs/implementation_plan.md`
2. Follow `AGENTS.md` and `/specs/IMPLEMENTATION_PROTOCOL.md`
3. Start with Phase 1 (Email Handler)

---

## Final Note

This system is built as:

**Deterministic Core + Agent Orchestration**

Not:

**Unbounded AI automation**
