## 1. Purpose

Defines the evidence acquisition tool group.

## 2. Scope

These tools fetch and normalize public-source evidence:

* company profile
* funding events
* job posts
* layoffs
* leadership changes
* tech stack
* public AI signals

## 3. Rules

* read-only
* public-data-only
* source metadata required
* no message generation
* no state mutation outside evidence persistence

## 4. Shared Output Requirements

All evidence tools SHOULD return:

```json
{
  "data": {},
  "source_meta": {
    "source_name": "string",
    "source_url": "string|null",
    "fetched_at": "timestamp"
  },
  "confidence_hint": 0.0
}
```

---