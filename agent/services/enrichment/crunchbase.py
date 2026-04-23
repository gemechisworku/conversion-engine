"""Crunchbase enrichment adapter."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.schemas import SignalSnapshot, SourceRef


class CrunchbaseAdapter:
    # Implements: FR-1, FR-2
    # Workflow: lead_intake_and_enrichment.md
    # Schema: evidence_record.md
    # API: research_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def collect(self, *, company_id: str, company_domain: str | None = None) -> SignalSnapshot:
        record = await self._load_record(company_id=company_id, company_domain=company_domain)
        if not record:
            return SignalSnapshot(
                summary={"company_id": company_id, "found": False},
                confidence=0.25,
                source_refs=[
                    SourceRef(source_name="crunchbase", source_url=self._settings.crunchbase_dataset_url or None)
                ],
            )
        confidence = 0.95 if record.get("company_id") == company_id else 0.8
        return SignalSnapshot(
            summary={
                "company_id": record.get("company_id") or company_id,
                "company_name": record.get("company_name"),
                "domain": record.get("domain"),
                "industry": record.get("industry"),
                "funding_round": record.get("funding_round"),
                "funding_amount_usd": record.get("funding_amount_usd"),
                "funding_date": record.get("funding_date"),
                "location": record.get("location"),
            },
            confidence=confidence,
            source_refs=[
                SourceRef(
                    source_name="crunchbase",
                    source_url=str(record.get("source_url") or self._settings.crunchbase_dataset_url or ""),
                )
            ],
        )

    async def _load_record(self, *, company_id: str, company_domain: str | None) -> dict[str, Any] | None:
        if self._settings.crunchbase_dataset_path:
            path = Path(self._settings.crunchbase_dataset_path)
            if path.exists():
                return self._load_from_file(path=path, company_id=company_id, company_domain=company_domain)
        if self._settings.crunchbase_dataset_url:
            return await self._load_from_url(
                url=self._settings.crunchbase_dataset_url,
                company_id=company_id,
                company_domain=company_domain,
            )
        return None

    def _load_from_file(
        self,
        *,
        path: Path,
        company_id: str,
        company_domain: str | None,
    ) -> dict[str, Any] | None:
        if path.suffix.lower() == ".json":
            rows = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                return None
            return self._match_record(rows=rows, company_id=company_id, company_domain=company_domain)
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return self._match_record(rows=list(reader), company_id=company_id, company_domain=company_domain)

    async def _load_from_url(
        self,
        *,
        url: str,
        company_id: str,
        company_domain: str | None,
    ) -> dict[str, Any] | None:
        response = await self._get(url=url)
        if not response.is_success:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        rows: list[dict[str, Any]]
        if isinstance(payload, dict):
            rows = [payload]
        elif isinstance(payload, list):
            rows = [row for row in payload if isinstance(row, dict)]
        else:
            return None
        return self._match_record(rows=rows, company_id=company_id, company_domain=company_domain)

    @staticmethod
    def _match_record(
        *,
        rows: list[dict[str, Any]],
        company_id: str,
        company_domain: str | None,
    ) -> dict[str, Any] | None:
        for row in rows:
            row_company_id = str(row.get("company_id") or row.get("id") or "").strip()
            row_domain = str(row.get("domain") or "").strip().lower()
            if row_company_id and row_company_id == company_id:
                return row
            if company_domain and row_domain and row_domain == company_domain.lower():
                return row
        return None

    async def _get(self, *, url: str) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.get(url)

