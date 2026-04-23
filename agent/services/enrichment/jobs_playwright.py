"""Public job-page collector."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.schemas import SignalSnapshot, SourceRef

ROLE_PATTERN = re.compile(r"<[^>]+>|\s+")


class JobsPlaywrightCollector:
    # Implements: FR-2
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

    async def collect(self, *, company_domain: str) -> SignalSnapshot:
        urls = [
            f"https://{company_domain}/careers",
            f"https://{company_domain}/jobs",
        ]
        html_pages: list[tuple[str, str]] = []
        for url in urls:
            html = await self._fetch_html(url=url)
            if html:
                html_pages.append((url, html))

        if not html_pages:
            return SignalSnapshot(
                summary={
                    "engineering_role_count": 0,
                    "ai_adjacent_role_count": 0,
                    "role_titles": [],
                    "scrape_timestamp": datetime.now(UTC).isoformat(),
                    "source_urls": urls,
                },
                confidence=0.3,
                source_refs=[SourceRef(source_name="jobs_playwright", source_url=url) for url in urls],
            )

        role_titles = self._extract_role_titles([html for _, html in html_pages])
        engineering_roles = [title for title in role_titles if self._is_engineering_role(title)]
        ai_adjacent_roles = [title for title in role_titles if self._is_ai_adjacent(title)]
        confidence = 0.85 if role_titles else 0.45
        return SignalSnapshot(
            summary={
                "engineering_role_count": len(engineering_roles),
                "ai_adjacent_role_count": len(ai_adjacent_roles),
                "role_titles": role_titles[:25],
                "scrape_timestamp": datetime.now(UTC).isoformat(),
                "source_urls": [url for url, _ in html_pages],
            },
            confidence=confidence,
            source_refs=[SourceRef(source_name="jobs_playwright", source_url=url) for url, _ in html_pages],
        )

    async def _fetch_html(self, *, url: str) -> str | None:
        try:
            response = await self._get(url=url)
            if response.is_success and "text/html" in response.headers.get("Content-Type", "text/html"):
                return response.text
        except httpx.HTTPError:
            pass
        return None

    async def _get(self, *, url: str) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.get(url)

    @staticmethod
    def _extract_role_titles(html_pages: list[str]) -> list[str]:
        role_titles: list[str] = []
        for html in html_pages:
            matches = re.findall(
                r"(?i)(Senior|Staff|Lead|Principal)?\s*(Data|ML|AI|Software|Backend|Frontend|Platform)[^<\n]{0,60}",
                html,
            )
            for match in matches:
                title = " ".join(part for part in match if part).strip()
                normalized = ROLE_PATTERN.sub(" ", title).strip()
                if normalized and normalized not in role_titles:
                    role_titles.append(normalized)
        return role_titles

    @staticmethod
    def _is_engineering_role(title: str) -> bool:
        lower = title.lower()
        return any(token in lower for token in ("software", "backend", "frontend", "platform", "ml", "data"))

    @staticmethod
    def _is_ai_adjacent(title: str) -> bool:
        lower = title.lower()
        return any(token in lower for token in ("ai", "ml", "machine learning", "data"))
