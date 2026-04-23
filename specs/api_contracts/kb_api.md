## 1. Purpose

Defines contracts for KB read/write/search operations.

---

## 2. Endpoints

## `GET /kb/page`

Query params:

* `path`

## `POST /kb/page`

### Request

```json
{
  "path": "kb/companies/acme.md",
  "content": "string",
  "mode": "replace"
}
```

## `POST /kb/search`

### Request

```json
{
  "query": "recent funding AI hiring healthcare",
  "limit": 10
}
```

---