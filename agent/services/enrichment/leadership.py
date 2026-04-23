"""Leadership-change signal adapter."""

from __future__ import annotations

import json
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

    async def collect(self, *, company_name: str) -> SignalSnapshot:
        entries = await self._load_entries()
        normalized = company_name.strip().lower()
        matched = [
            entry
            for entry in entries
            if str(entry.get("company") or entry.get("company_name") or "").strip().lower() == normalized
        ]
        if not matched:
            return SignalSnapshot(
                summary={
                    "matched": False,
                    "company_name": company_name,
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

    async def _get(self, *, url: str) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.get(url)

