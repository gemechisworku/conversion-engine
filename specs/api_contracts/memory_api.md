## 1. Purpose

Defines contracts for state persistence, compaction, and rehydration.

---

## 2. Endpoints

## `POST /memory/session/write`

### Request

```json
{
  "lead_id": "lead_123",
  "session_state": {}
}
```

## `GET /memory/session/{lead_id}`

Returns current session state.

## `POST /memory/compact`

### Request

```json
{
  "lead_id": "lead_123",
  "reason": "phase_boundary"
}
```

## `POST /memory/rehydrate`

### Request

```json
{
  "lead_id": "lead_123"
}
```

---