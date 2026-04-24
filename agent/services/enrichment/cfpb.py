"""CFPB complaint enrichment for financial-services prospects."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.schemas import ComplianceBrief, ComplianceIssue, EnrichmentBrief, SourceRef

FINANCIAL_INDUSTRY_TERMS = {
    "bank",
    "banking",
    "credit",
    "finance",
    "financial",
    "fintech",
    "insurance",
    "lending",
    "loan",
    "mortgage",
    "payments",
    "wealth",
}


class CFPBComplaintAdapter:
    # Implements: FR-2, FR-16
    # Workflow: reply_handling.md
    # Schema: evidence_record.md
    # API: research_api.md
    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    async def build_compliance_brief(
        self,
        *,
        lead_id: str,
        enrichment_brief: EnrichmentBrief,
        lookback_days: int = 180,
    ) -> ComplianceBrief:
        company_name = enrichment_brief.firmographics.company_name
        if not self._is_financial_services(enrichment_brief=enrichment_brief):
            return ComplianceBrief(
                brief_id=f"compliance_{uuid4().hex[:10]}",
                lead_id=lead_id,
                company_id=enrichment_brief.company_id,
                applicable=False,
                company_name=company_name,
                lookback_days=lookback_days,
                skipped_reason="not_financial_services",
                confidence=0.8 if enrichment_brief.matched else 0.4,
                source_refs=[],
            )
        if not company_name:
            return ComplianceBrief(
                brief_id=f"compliance_{uuid4().hex[:10]}",
                lead_id=lead_id,
                company_id=enrichment_brief.company_id,
                applicable=True,
                company_name=None,
                lookback_days=lookback_days,
                skipped_reason="missing_company_name",
                confidence=0.0,
                risk_notes=["Cannot query CFPB without a company name."],
            )
        try:
            rows = await self._query(company_name=company_name, lookback_days=lookback_days)
        except httpx.HTTPError as exc:
            return ComplianceBrief(
                brief_id=f"compliance_{uuid4().hex[:10]}",
                lead_id=lead_id,
                company_id=enrichment_brief.company_id,
                applicable=True,
                company_name=company_name,
                lookback_days=lookback_days,
                confidence=0.0,
                error=str(exc),
                risk_notes=["CFPB lookup failed; do not make compliance-specific claims."],
                source_refs=[SourceRef(source_name="cfpb_complaints", source_url=self._settings.cfpb_api_url)],
            )

        top_issues = self._top_issues(rows=rows)
        return ComplianceBrief(
            brief_id=f"compliance_{uuid4().hex[:10]}",
            lead_id=lead_id,
            company_id=enrichment_brief.company_id,
            applicable=True,
            company_name=company_name,
            lookback_days=lookback_days,
            complaint_count=len(rows),
            top_issues=top_issues,
            confidence=0.85 if rows else 0.65,
            source_refs=[SourceRef(source_name="cfpb_complaints", source_url=self._settings.cfpb_api_url)],
            risk_notes=[] if rows else ["No CFPB complaints found in the lookback window."],
        )

    def _is_financial_services(self, *, enrichment_brief: EnrichmentBrief) -> bool:
        industries = " ".join(enrichment_brief.firmographics.industries).lower()
        industry = (enrichment_brief.firmographics.industry or "").lower()
        text = f"{industries} {industry}"
        return any(term in text for term in FINANCIAL_INDUSTRY_TERMS)

    async def _query(self, *, company_name: str, lookback_days: int) -> list[dict[str, Any]]:
        since = (datetime.now(UTC) - timedelta(days=lookback_days)).date().isoformat()
        params = {
            "field": "all",
            "format": "json",
            "no_aggs": "true",
            "size": str(self._settings.cfpb_result_limit),
            "company": company_name,
            "date_received_min": since,
        }
        response = await self._get(url=self._settings.cfpb_api_url, params=params)
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("hits", {}).get("hits", []) if isinstance(payload, dict) else []
        rows: list[dict[str, Any]] = []
        for hit in hits:
            if isinstance(hit, dict) and isinstance(hit.get("_source"), dict):
                rows.append(hit["_source"])
        return rows

    async def _get(self, *, url: str, params: dict[str, str]) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, params=params, timeout=self._settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.get(url, params=params)

    @staticmethod
    def _top_issues(*, rows: list[dict[str, Any]]) -> list[ComplianceIssue]:
        counter: Counter[str] = Counter()
        product_by_issue: dict[str, str] = {}
        for row in rows:
            issue = str(row.get("issue") or "").strip()
            if not issue:
                continue
            counter[issue] += 1
            product = str(row.get("product") or "").strip()
            if product and issue not in product_by_issue:
                product_by_issue[issue] = product
        return [
            ComplianceIssue(issue=issue, count=count, sample_product=product_by_issue.get(issue))
            for issue, count in counter.most_common(3)
        ]
