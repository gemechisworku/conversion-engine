## 1. Purpose

Defines contracts for CRM record creation, update, and event logging.

---

## 2. Endpoints

## `POST /crm/lead`

Create or update lead.

## `POST /crm/event`

Append CRM event.

### Request

```json
{
  "lead_id": "lead_123",
  "event_type": "reply_received",
  "event_key": "msg_123",
  "payload": {
    "channel": "email"
  }
}
```

### Response

```json
{
  "request_id": "req_501",
  "trace_id": "trace_501",
  "status": "success",
  "data": {
    "crm_event_id": "crm_evt_123"
  },
  "error": null,
  "timestamp": "timestamp"
}
```

## `POST /crm/stage`

Update lead stage.

---

# `api_contracts/scheduling_api.md`

## 1. Purpose

Defines contracts for slot lookup, proposal, and booking.

---

## 2. Endpoints

## `POST /schedule/slots`

### Request

```json
{
  "lead_id": "lead_123",
  "timezone": "America/New_York",
  "window_start": "timestamp",
  "window_end": "timestamp"
}
```

### Response

```json
{
  "request_id": "req_601",
  "trace_id": "trace_601",
  "status": "success",
  "data": {
    "slots": [
      {
        "slot_id": "slot_1",
        "start_at": "timestamp",
        "end_at": "timestamp"
      }
    ]
  },
  "error": null,
  "timestamp": "timestamp"
}
```

## `POST /schedule/book`

### Request

```json
{
  "lead_id": "lead_123",
  "slot_id": "slot_1",
  "confirmed_by_prospect": true
}
```

### Response

```json
{
  "request_id": "req_602",
  "trace_id": "trace_602",
  "status": "success",
  "data": {
    "booking_id": "booking_123",
    "status": "confirmed"
  },
  "error": null,
  "timestamp": "timestamp"
}
```

---
