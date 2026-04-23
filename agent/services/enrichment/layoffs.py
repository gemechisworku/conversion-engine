"""Layoff signal adapter."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.schemas import SignalSnapshot, SourceRef


class LayoffsAdapter:
    # Implements: FR-2
    # Workflow: lead_intake_and_enrichment.md
    # Schema: evidence_record.md
    # API: research_api.md
    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    async def collect(self, *, company_name: str) -> SignalSnapshot:
        rows = await self._load_rows()
        if not rows:
            return SignalSnapshot(
                summary={"matched": False, "company_name": company_name},
                confidence=0.3,
                source_refs=[SourceRef(source_name="layoffs_fyi", source_url=self._settings.layoffs_csv_url or None)],
            )
        normalized_name = company_name.strip().lower()
        match = None
        for row in rows:
            row_name = str(row.get("company") or row.get("company_name") or "").strip().lower()
            if not row_name:
                continue
            if row_name == normalized_name:
                match = row
                break
        if not match:
            return SignalSnapshot(
                summary={"matched": False, "company_name": company_name},
                confidence=0.65,
                source_refs=[SourceRef(source_name="layoffs_fyi", source_url=self._settings.layoffs_csv_url or None)],
            )

        affected_count = self._coerce_int(match.get("laid_off") or match.get("affected_count"))
        confidence = 0.9 if affected_count is not None else 0.7
        return SignalSnapshot(
            summary={
                "matched": True,
                "company_name": company_name,
                "layoff_date": match.get("date"),
                "affected_count": affected_count,
                "affected_percent": self._coerce_float(match.get("%")),
            },
            confidence=confidence,
            source_refs=[SourceRef(source_name="layoffs_fyi", source_url=self._settings.layoffs_csv_url or None)],
        )

    async def _load_rows(self) -> list[dict[str, Any]]:
        if self._settings.layoffs_csv_path:
            path = Path(self._settings.layoffs_csv_path)
            if path.exists():
                with path.open("r", encoding="utf-8", newline="") as handle:
                    return list(csv.DictReader(handle))
        if self._settings.layoffs_csv_url:
            response = await self._get(url=self._settings.layoffs_csv_url)
            if response.is_success:
                text = response.text
                return list(csv.DictReader(text.splitlines()))
        return []

    async def _get(self, *, url: str) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.get(url)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(str(value).replace(",", "").strip())
        except ValueError:
            return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        text = str(value).replace("%", "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

