## 1. Purpose

Assign the lead to the best-fit Tenacious ICP segment with confidence and abstention support.

## 2. Responsibilities

* determine primary segment
* propose alternate segment
* abstain when evidence is ambiguous

## 3. Allowed Tools

* classify_icp
* kb_read_page
* observability tools

## 4. Rules

* MUST not force a segment when contradictory signals materially affect pitch choice
* MUST explain primary and alternate segment rationale

## 5. Output

```json
{
  "classification_id": "string",
  "primary_segment": "recently_funded_startup",
  "alternate_segment": "cost_restructure",
  "confidence": 0.58,
  "abstain": false,
  "rationale": []
}
```

---