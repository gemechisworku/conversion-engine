"""Layoff signal adapter."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
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

    async def collect(self, *, company_name: str, crunchbase_row: dict[str, Any] | None = None) -> SignalSnapshot:
        rows = await self._load_rows()
        if not rows and crunchbase_row is not None:
            rows = self._rows_from_crunchbase(row=crunchbase_row)
        if not rows:
            return SignalSnapshot(
                summary={"matched": False, "company_name": company_name, "window_days": 120},
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
        if match and not self._within_days(match.get("date"), days=120):
            match = None
        if not match:
            return SignalSnapshot(
                summary={"matched": False, "company_name": company_name, "window_days": 120},
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
                "window_days": 120,
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

    @staticmethod
    def _rows_from_crunchbase(*, row: dict[str, Any]) -> list[dict[str, Any]]:
        raw = row.get("layoff")
        if raw is None:
            return []
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            return []
        if parsed in (None, [], {}):
            return []
        items = parsed if isinstance(parsed, list) else [parsed]
        rows: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "company": row.get("name") or row.get("company_name"),
                    "date": item.get("date") or item.get("announced_on") or item.get("layoff_date"),
                    "laid_off": item.get("laid_off") or item.get("affected_count"),
                    "%": item.get("%") or item.get("affected_percent"),
                }
            )
        return rows

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

    @staticmethod
    def _within_days(value: Any, *, days: int) -> bool:
        if not value:
            return False
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.strptime(text[:10], "%Y-%m-%d")
            except ValueError:
                return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC) >= datetime.now(UTC) - timedelta(days=days)
