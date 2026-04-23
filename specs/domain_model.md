## 1. Purpose

This document defines the business concepts used throughout the system.

It provides a shared language between:

* product logic
* agent behavior
* data models
* APIs
* workflows
* evaluation

---

## 2. Core Domain Entities

### 2.1 Company

A company is a public organization record used as the root object for prospect research.

Key properties:

* company_id
* company_name
* domain
* industry
* size_band
* geography
* funding history

---

### 2.2 Lead

A lead is the system’s operational representation of a target company/contact pathway.

A lead may contain:

* company linkage
* qualification status
* current workflow state
* segment classification
* AI maturity score
* CRM linkage
* conversation state

A lead is the primary orchestration object.

---

### 2.3 ICP Segment

An ICP segment is one of the fixed Tenacious prospect classes:

* recently funded startup
* cost restructuring / post-layoff mid-market
* leadership transition
* specialized capability gap

It influences:

* messaging strategy
* prioritization
* qualification framing

---

### 2.4 Signal

A signal is a public-data-backed indicator used to reason about prospect fit or timing.

Signal types include:

* funding event
* hiring velocity
* layoffs
* leadership change
* tech stack
* AI-related hiring or activity

Signals must include:

* summary
* confidence
* evidence refs

---

### 2.5 Evidence Record

An evidence record is the normalized representation of a source-backed fact or observation.

It is the lowest-level traceable unit supporting a claim.

---

### 2.6 Hiring Signal Brief

A hiring signal brief is the main synthesized research artifact for outreach generation.

It combines:

* signal summaries
* confidence
* AI maturity
* bench fit
* language guidance
* risk notes

---

### 2.7 Competitor Gap Brief

A competitor gap brief is a research artifact that compares the prospect to peers and identifies sector-relative gaps.

It exists to support research-led outreach rather than generic vendor messaging.

---

### 2.8 AI Maturity Score

A structured score from 0–3 indicating the prospect’s inferred level of AI engagement based on public evidence.

This score is:

* evidence-backed
* confidence-bearing
* non-authoritative
* messaging-relevant

---

### 2.9 Bench Match

A bench match is an assessment of alignment between the prospect’s likely needs and current Tenacious delivery capacity.

It is a decision-support object, not a permission to promise staffing.

---

### 2.10 Outreach Draft

An outreach draft is a candidate outbound message prepared for review and possible send.

It includes:

* body
* channel
* message purpose
* claim refs
* review status

---

### 2.11 Conversation State

Conversation state captures the current interaction stage between the system and the prospect.

It includes:

* last intent
* stage
* objections
* pending actions
* scheduling context

---

### 2.12 Session State

Session state is the compact operational summary of everything the system must remember to continue lead handling safely.

---

### 2.13 Booking

A booking is a confirmed discovery call reservation.

A booking requires:

* explicit prospect confirmation
* slot id
* booking id
* CRM linkage

---

### 2.14 Policy Decision

A policy decision is a structured record that an action was allowed, blocked, or escalated under system policy.

---

### 2.15 Handoff Package

A handoff package is the packaged escalation artifact sent to human operators when autonomous handling stops.

---

## 3. Entity Relationships

### Company → Lead

One company may correspond to one or more leads over time, but in this challenge design a single normalized lead per target company is preferred unless role-specific conversations require separation.

### Lead → Briefs

A lead may have:

* one current hiring signal brief
* one current competitor gap brief
* historical prior versions

### Lead → Conversation State

Each active lead has one current conversation state.

### Lead → Session State

Each active lead has one current session state.

### Lead → CRM Record

Each active lead should map to one CRM record.

### Lead → Policy Decisions

A lead may accumulate many policy decisions over time.

### Lead → Handoff Package

A lead may have zero or more handoff packages.

---

## 4. Domain Invariants

* every factual outbound claim must be evidence-backed or softened
* every active lead must have session state
* every sent outbound message must have review status
* every booking must have explicit prospect confirmation
* every stateful side effect must be logged

---