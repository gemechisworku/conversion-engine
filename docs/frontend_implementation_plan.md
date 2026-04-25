
# Frontend / Full-System Implementation Plan

---

## Stack & Brand

- **Framework:** Next.js (App Router)
- **Styling:** Tailwind CSS
- **Language:** TypeScript  
- **Brand:** Blue primary  
- **Theme:** Required dark + light mode
  - System preference (default)
  - Manual toggle
  - Persisted user choice

---

## Backend Context

Existing FastAPI orchestration:

- `ResponseEnvelope`
- Idempotency support
- Optional `ORCHESTRATION_API_KEY`
- CORS enabled
- Webhooks remain server-side

---

## 1. Objectives (Definition of Done)

| Horizon | Outcome |
|--------|--------|
| **MVP (Phase A)** | Ops can log in → view pipeline → open lead → inspect state, briefs, evidence → draft → review → send (if allowed) → escalate. Includes theme + accessibility baseline. |
| **Phase B** | Conversation desk with threads, reply-driven next actions, and pending actions surfaced. |
| **Phase C** | Scheduling UX + CRM status visibility (read-first, write where API allows). |
| **Phase D** | Control tower: handoff queue, trace/evidence exploration, exports for program staff. |

---

## 2. Design System Principles

### Tailwind Strategy

- Use **CSS variables** for theming:
  - `--color-bg`
  - `--color-surface`
  - `--color-text`
  - `--color-primary`
  - `--color-border`
  - `--color-danger`

- Apply via:
  - `:root` (light)
  - `[data-theme="dark"]` or `class="dark"`

### Color System

- Primary blue:
  - Light: `blue-600`
  - Dark: `blue-500`
- Maintain consistent hover/active ramps

### Typography

- Single sans-serif stack (e.g. Inter / Geist via `next/font`)
- Clear hierarchy:
  - Lead title
  - Metadata
  - Body

### Component System

Token-driven components:

- Button
- Card
- Badge (stage)
- Tabs
- DataTable
- Dialog
- Toast
- Skeleton

> Theme toggle should update all components via tokens (no hardcoded styles)

---

## 3. Next.js Setup

### App Router Structure

- `layout.tsx`:
  - Theme provider
  - `suppressHydrationWarning` on `<html>`

### Theme Handling

- Use `next-themes` or equivalent:
  - `defaultTheme="system"`
  - `enableSystem`
  - Persist preference
- Theme toggle in header

### Rules

- No hardcoded hex values outside theme config

---

## 4. Application Architecture

```

app/
(auth)/login/
(dashboard)/
layout.tsx          # sidebar, header, theme toggle
page.tsx            # pipeline home
leads/[leadId]/     # overview | briefs | outreach | conversation | evidence
settings/           # API config, feature flags

lib/
api-client.ts         # fetch wrapper, envelope parsing, trace logging
types/envelope.ts     # ResponseEnvelope types

components/
ui/                   # primitives
domain/               # LeadStageBadge, BriefPanel, EvidenceList

```

### API Strategy

- Start with **direct browser → FastAPI**
- Add **BFF (Next Route Handlers)** later if needed:
  - Hide API keys
  - Add SSO

### Environment Variables

- `NEXT_PUBLIC_ORCHESTRATION_API_URL`
- Only client-safe values exposed
- Secrets handled server-side if BFF added

---

## 5. Epic Breakdown

### Epic 0 — Foundation (Week 0–1)

- Next.js + Tailwind + strict TypeScript
- ESLint + Prettier
- Theme system (dark/light)
- Root layout + dashboard shell
- API client + error handling (toasts)
- Health check page (`GET /health`)

---

### Epic 1 — Auth & Shell (Week 1)

- Login page:
  - API key input
  - Store in sessionStorage or cookie
- Sidebar navigation:
  - Pipeline
  - Settings (placeholder)
- Header:
  - User menu
  - Theme toggle

---

### Epic 2 — Pipeline (Week 1–2)

- Lead list view

**Current API gap:**
- No `GET /leads`

**MVP workaround:**
- Option A: Manual “Process Lead” (`POST /lead/process`)
- Option B: Add backend endpoint later

**Features:**
- Stage badges
- Filters by stage
- Mapping from `state_machines.md`

---

### Epic 3 — Lead Overview (Week 2)

- Fetch: `GET /lead/{id}/state`

**UI includes:**
- Company
- Stage
- Segment
- Confidence
- AI score
- Pending actions
- Policy flags

- External CRM link (HubSpot)

---

### Epic 4 — Research & Briefs (Week 2–3)

Tabs:

- Signals
- Hiring Brief
- Competitor Gap

Features:

- JSON → UI rendering
- Confidence chips
- Evidence references

API:
- `GET /memory/evidence/{leadId}`

---

### Epic 5 — Outreach Studio (Week 3–4)

Flow:

1. Advance to drafting
2. `POST /outreach/draft`
3. Display draft
4. `POST /outreach/review`
5. Display review record
6. `POST /outreach/send`

Features:

- Confirmation dialogs
- Policy enforcement (FR-8, FR-16)
- Client-side idempotency keys (UUID)

---

### Epic 6 — Conversation Desk (Week 4–6)

- Thread UI

**If API not ready:**
- Stub UI
- Use `POST /lead/reply` manually

Features:

- Display `next_best_action`
- Action buttons → `POST /lead/advance`
- Client-side transition allow-list

---

### Epic 7 — Escalation & Handoff (Week 5–6)

- `POST /lead/escalate`

Fields:

- `reason_code`
- `summary`
- `evidence_refs`

Pipeline filter:

- `handoff_required`

---

### Epic 8 — Memory & Compaction (Week 6)

- Session tools:
  - GET/POST memory session
  - Compact
  - Rehydrate

- Hidden under “Advanced” UI

---

### Epic 9 — Scheduling & CRM (Phase C)

- Cal.com integration (embed or link)
- Booking fields from API
- CRM timeline (when available)

---

### Epic 10 — Observability (Phase D)

- Trace ID visibility
- Future:
  - Cost tracking
  - Charts from observability API

---

## 6. Full-System Tracks (Parallel Work)

| Track | Owner | Notes |
|------|------|------|
| GET /leads | Backend | Enables real pipeline |
| SSO / JWT | Backend + Next | Replace API keys |
| Webhooks | Backend | Ensure idempotency + correlation IDs |
| E2E Testing | QA | Playwright with staging or mocks |

---

## 7. Quality Bar

### Accessibility (A11y)

- Visible focus states
- Full keyboard navigation
- Proper color contrast (both themes)

### Testing

- Unit: Vitest + React Testing Library
- E2E: Playwright
  - Login
  - Process lead
  - Open lead detail

### Deployment

- Next.js → Vercel / Node
- Environment-specific configs
- FastAPI CORS updated per environment

---

## 8. Milestone Checklist

- [ ] Next.js repo (`apps/web` or `frontend/`)
- [ ] Tailwind + theme system
- [ ] API client + envelope handling
- [ ] Dashboard shell + auth
- [ ] Lead processing flow
- [ ] Lead detail + state panel
- [ ] Briefs + evidence UI
- [ ] Outreach (draft → review → send)
- [ ] Conversation + escalation
- [ ] Scheduling / CRM / observability (as APIs arrive)

---

## Summary

This plan outlines a phased frontend system built with:

- **Next.js + Tailwind**
- **Blue primary design system**
- **Mandatory dark/light theming**
- **Progressive rollout from ops console → conversation → scheduling → control tower**

It also highlights critical backend dependencies:

- `GET /leads`
- SSO/JWT
- Optional BFF layer

The goal is to ensure the frontend is **not blocked by backend limitations** and can evolve incrementally while maintaining production quality.

