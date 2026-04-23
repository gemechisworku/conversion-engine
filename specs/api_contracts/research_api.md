## 1. Purpose

Defines API contracts for evidence collection, normalization, and research synthesis.

---

## 2. Endpoints

## `POST /research/enrich`

Collect and normalize public evidence for a company.

### Request

```json
{
  "company_id": "string",
  "domain": "string|null",
  "window_config": {
    "funding_days": 180,
    "jobs_days": 60,
    "layoff_days": 120,
    "leadership_days": 90
  }
}
```

### Response

```json
{
  "request_id": "req_201",
  "trace_id": "trace_201",
  "status": "success",
  "data": {
    "evidence_packet_id": "evpkt_123",
    "company_id": "string",
    "signals_collected": ["funding", "jobs", "layoffs", "leadership", "stack"]
  },
  "error": null,
  "timestamp": "timestamp"
}
```

## `GET /research/evidence/{evidence_packet_id}`

Return normalized evidence packet.

## `POST /research/brief`

Generate hiring signal brief from an evidence packet.

### Request

```json
{
  "lead_id": "lead_123",
  "company_id": "company_123",
  "evidence_packet_id": "evpkt_123"
}
```

### Response

```json
{
  "request_id": "req_202",
  "trace_id": "trace_202",
  "status": "success",
  "data": {
    "brief_id": "brief_123"
  },
  "error": null,
  "timestamp": "timestamp"
}
```

---
