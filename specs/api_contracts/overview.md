# **1. Design Principles**

* All APIs must be:

  * typed
  * idempotent (where applicable)
  * traceable
* Responses MUST include:

  * request_id
  * timestamp
  * status
  * data
  * errors (if any)

---

## **2. Orchestration API**

### `POST /lead/process`

Process a new lead end-to-end

**Request**

```json
{
  "company_id": "string",
  "source": "crunchbase",
  "priority": "normal"
}
```

**Response**

```json
{
  "lead_id": "string",
  "status": "processing",
  "trace_id": "string"
}
```

---

## **3. Research API**

### `POST /research/enrich`

```json
{
  "company_id": "string"
}
```

**Response**

```json
{
  "signals": {
    "funding": {...},
    "jobs": {...},
    "layoffs": {...}
  },
  "confidence": {...}
}
```

---

## **4. Scoring API**

### `POST /score/ai-maturity`

```json
{
  "signals": {...}
}
```

**Response**

```json
{
  "score": 2,
  "confidence": 0.7,
  "justification": [...]
}
```

---

## **5. Outreach API**

### `POST /outreach/draft`

```json
{
  "lead_id": "string",
  "brief_id": "string",
  "variant": "cold_email"
}
```

**Response**

```json
{
  "draft_id": "string",
  "content": "string",
  "confidence_flags": [...]
}
```

---

## **6. CRM API**

### `POST /crm/lead`

```json
{
  "lead": {...}
}
```

---

## **7. Scheduling API**

### `POST /schedule/book`

```json
{
  "lead_id": "string",
  "slot_id": "string"
}
```

---

## **8. KB API**

### `GET /kb/page`

```json
{
  "path": "kb/companies/x.md"
}
```

---

## **9. Observability API**

### `POST /trace/event`

```json
{
  "event_type": "tool_call",
  "payload": {...}
}
```