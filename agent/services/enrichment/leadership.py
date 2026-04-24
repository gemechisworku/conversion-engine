"""Leadership-change signal adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.schemas import SignalSnapshot, SourceRef


class LeadershipChangeDetector:
    # Implements: FR-2
    # Workflow: lead_intake_and_enrichment.md
    # Schema: evidence_record.md
    # API: research_api.md
    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    async def collect(self, *, company_name: str, crunchbase_row: dict[str, Any] | None = None) -> SignalSnapshot:
        entries = await self._load_entries()
        if crunchbase_row is not None:
            entries = [*entries, *self._entries_from_crunchbase(row=crunchbase_row)]
        normalized = company_name.strip().lower()
        matched = [
            entry
            for entry in entries
            if str(entry.get("company") or entry.get("company_name") or "").strip().lower() == normalized
            and self._is_target_role(str(entry.get("role_name") or ""))
            and self._within_days(entry.get("change_date") or entry.get("date"), days=90)
        ]
        if not matched:
            return SignalSnapshot(
                summary={
                    "matched": False,
                    "company_name": company_name,
                    "window_days": 90,
                },
                confidence=0.5,
                source_refs=[SourceRef(source_name="leadership_public", source_url=self._settings.leadership_feed_url)],
            )
        latest = matched[0]
        confidence = 0.82 if latest.get("change_date") else 0.65
        return SignalSnapshot(
            summary={
                "matched": True,
                "company_name": company_name,
                "role_name": latest.get("role_name"),
                "person": latest.get("person"),
                "change_type": latest.get("change_type"),
                "date": latest.get("change_date"),
                "window_days": 90,
            },
            confidence=confidence,
            source_refs=[
                SourceRef(
                    source_name="leadership_public",
                    source_url=str(latest.get("source_url") or self._settings.leadership_feed_url or ""),
                )
            ],
        )

    async def _load_entries(self) -> list[dict[str, Any]]:
        if self._settings.leadership_feed_url:
            if self._settings.leadership_feed_url.startswith(("http://", "https://")):
                response = await self._get(url=self._settings.leadership_feed_url)
                if response.is_success:
                    try:
                        payload = response.json()
                        if isinstance(payload, list):
                            return [entry for entry in payload if isinstance(entry, dict)]
                    except ValueError:
                        return []
            else:
                path = Path(self._settings.leadership_feed_url)
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        return [entry for entry in data if isinstance(entry, dict)]
        return []

    @staticmethod
    def _entries_from_crunchbase(*, row: dict[str, Any]) -> list[dict[str, Any]]:
        raw = row.get("leadership_hire")
        if raw is None:
            return []
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            return []
        if parsed in (None, [], {}):
            return []
        items = parsed if isinstance(parsed, list) else [parsed]
        entries: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            entries.append(
                {
                    "company": row.get("name") or row.get("company_name"),
                    "role_name": item.get("role_name") or item.get("title") or item.get("role"),
                    "person": item.get("person") or item.get("name"),
                    "change_type": item.get("change_type") or "leadership_hire",
                    "change_date": item.get("date") or item.get("announced_on") or item.get("created_at"),
                    "source_url": row.get("url"),
                }
            )
        return entries

    @staticmethod
    def _is_target_role(role_name: str) -> bool:
        lower = role_name.lower()
        return any(token in lower for token in ("cto", "chief technology", "vp engineering", "vp of engineering"))

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

    async def _get(self, *, url: str) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.get(url)
