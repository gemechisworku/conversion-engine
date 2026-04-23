## 1. Purpose

Defines contracts for scoring, classification, and related reasoning outputs.

---

## 2. Endpoints

## `POST /score/ai-maturity`

### Request

```json
{
  "company_id": "company_123",
  "evidence_packet_id": "evpkt_123"
}
```

### Response

```json
{
  "request_id": "req_301",
  "trace_id": "trace_301",
  "status": "success",
  "data": {
    "score_id": "score_123",
    "score": 2,
    "confidence": 0.66
  },
  "error": null,
  "timestamp": "timestamp"
}
```

## `POST /score/icp-classify`

### Request

```json
{
  "lead_id": "lead_123",
  "brief_id": "brief_123",
  "score_id": "score_123"
}
```

### Response

```json
{
  "request_id": "req_302",
  "trace_id": "trace_302",
  "status": "success",
  "data": {
    "classification_id": "class_123",
    "primary_segment": "recently_funded_startup",
    "alternate_segment": "leadership_transition",
    "confidence": 0.58,
    "abstain": false
  },
  "error": null,
  "timestamp": "timestamp"
}
```

## `POST /score/competitor-gap`

### Request

```json
{
  "lead_id": "lead_123",
  "company_id": "company_123",
  "brief_id": "brief_123"
}
```

### Response

```json
{
  "request_id": "req_303",
  "trace_id": "trace_303",
  "status": "success",
  "data": {
    "gap_brief_id": "gap_123",
    "sector_percentile": 0.39,
    "confidence": 0.62
  },
  "error": null,
  "timestamp": "timestamp"
}
```

---