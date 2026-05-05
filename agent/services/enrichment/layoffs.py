"""Layoff signal adapter."""

from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.event_extractor import EventExtractor
from agent.services.enrichment.schemas import SignalSnapshot, SourceRef

DEFAULT_LAYOFFS_FYI_URL = "https://layoffs.fyi/"


class LayoffsAdapter:
    # Implements: FR-2
    # Workflow: lead_intake_and_enrichment.md
    # Schema: evidence_record.md
    # API: research_api.md
    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client
        self._event_extractor = EventExtractor()

    async def collect(self, *, company_name: str, crunchbase_row: dict[str, Any] | None = None) -> SignalSnapshot:
        reference_now = self._reference_now()
        rows, source_name, source_url = await self._load_rows()
        if not rows and crunchbase_row is not None:
            rows = self._rows_from_crunchbase_with_events(
                row=crunchbase_row,
                reference_now=reference_now,
            )
            source_name = "crunchbase_fallback"
            source_url = str(crunchbase_row.get("url") or crunchbase_row.get("source_url") or "")
        if not rows:
            return SignalSnapshot(
                summary={"matched": False, "company_name": company_name, "window_days": 120},
                confidence=0.3,
                source_refs=[
                    SourceRef(
                        source_name=source_name,
                        source_url=source_url or None,
                    )
                ],
            )
        normalized_name = self._normalize_company_name(company_name)
        match = None
        for row in rows:
            row_name = self._normalize_company_name(str(row.get("company") or row.get("company_name") or ""))
            if not row_name:
                continue
            if row_name == normalized_name or normalized_name in row_name or row_name in normalized_name:
                match = row
                break
        if match and not self._within_days(match.get("date"), days=120, reference_now=reference_now):
            match = None
        if not match:
            return SignalSnapshot(
                summary={"matched": False, "company_name": company_name, "window_days": 120},
                confidence=0.65,
                source_refs=[SourceRef(source_name=source_name, source_url=source_url or None)],
            )

        affected_count = self._coerce_int(match.get("laid_off") or match.get("affected_count"))
        confidence = 0.9 if affected_count is not None else 0.7
        match_source_url = str(match.get("source_url") or source_url or "").strip() or None
        return SignalSnapshot(
            summary={
                "matched": True,
                "company_name": company_name,
                "layoff_date": match.get("date"),
                "affected_count": affected_count,
                "affected_percent": self._coerce_float(match.get("%")),
                "source_url": match_source_url,
                "window_days": 120,
            },
            confidence=confidence,
            source_refs=[SourceRef(source_name=source_name, source_url=match_source_url)],
        )

    async def _load_rows(self) -> tuple[list[dict[str, Any]], str, str]:
        if self._settings.layoffs_csv_path:
            path = Path(self._settings.layoffs_csv_path)
            if path.exists():
                with path.open("r", encoding="utf-8", newline="") as handle:
                    return list(csv.DictReader(handle)), "layoffs_fyi", str(path)
        if self._settings.layoffs_csv_url:
            try:
                response = await self._get(url=self._settings.layoffs_csv_url)
            except httpx.HTTPError:
                response = None
            if response is not None and response.is_success:
                text = response.text
                return list(csv.DictReader(text.splitlines())), "layoffs_fyi", self._settings.layoffs_csv_url
        try:
            response = await self._get(url=DEFAULT_LAYOFFS_FYI_URL)
        except httpx.HTTPError:
            response = None
        if response is not None and response.is_success:
            rows = self._rows_from_layoffs_fyi_html(response.text)
            if rows:
                return rows, "layoffs_fyi", DEFAULT_LAYOFFS_FYI_URL
        return [], "layoffs_fyi", self._settings.layoffs_csv_url or DEFAULT_LAYOFFS_FYI_URL

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
                    "date": item.get("date") or item.get("announced_on") or item.get("layoff_date") or item.get("key_event_date"),
                    "laid_off": item.get("laid_off") or item.get("affected_count"),
                    "%": item.get("%") or item.get("affected_percent"),
                    "source_url": item.get("link") or row.get("url") or row.get("source_url"),
                }
            )
        return rows

    def _rows_from_crunchbase_with_events(
        self,
        *,
        row: dict[str, Any],
        reference_now: datetime,
    ) -> list[dict[str, Any]]:
        candidates = self._event_extractor.normalize(
            row=row,
            source_url=str(row.get("url") or row.get("source_url") or "") or None,
        )
        events = self._event_extractor.extract_layoff_events(candidates=candidates)
        events = self._event_extractor.events_within_days(events=events, days=120, reference_now=reference_now)
        rows: list[dict[str, Any]] = []
        for event in events:
            extracted = event.extracted_values
            rows.append(
                {
                    "company": row.get("name") or row.get("company_name"),
                    "date": event.event_date,
                    "laid_off": extracted.get("affected_count"),
                    "%": extracted.get("affected_pct"),
                    "source_url": event.source_url or row.get("url") or row.get("source_url"),
                }
            )
        if rows:
            return rows
        return self._rows_from_crunchbase(row=row)

    @staticmethod
    def _rows_from_layoffs_fyi_html(html: str) -> list[dict[str, Any]]:
        if not html.strip():
            return []
        rows: list[dict[str, Any]] = []
        table_row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
        cell_pattern = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
        tag_pattern = re.compile(r"<[^>]+>")
        for row_html in table_row_pattern.findall(html):
            cells = [tag_pattern.sub(" ", raw).strip() for raw in cell_pattern.findall(row_html)]
            if len(cells) < 3:
                continue
            company = cells[0]
            date = cells[1]
            laid_off = cells[2]
            if not company or company.lower() == "company":
                continue
            rows.append({"company": company, "date": date, "laid_off": laid_off})
        return rows

    async def _get(self, *, url: str) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
        async with httpx.AsyncClient(
            timeout=self._settings.http_timeout_seconds,
            trust_env=self._settings.http_trust_env_proxy,
        ) as client:
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
    def _within_days(value: Any, *, days: int, reference_now: datetime | None = None) -> bool:
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
        now = reference_now or datetime.now(UTC)
        return parsed.astimezone(UTC) >= now - timedelta(days=days)

    def _reference_now(self) -> datetime:
        value = self._settings.enrichment_reference_date.strip()
        if not value:
            return datetime.now(UTC)
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(UTC)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _normalize_company_name(value: str) -> str:
        text = value.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|plc)\b", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
