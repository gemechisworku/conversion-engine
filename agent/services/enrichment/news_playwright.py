"""Playwright-backed public news/filing retrieval."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.schemas import EnrichmentBrief, NewsBrief, SourceRef


class PublicNewsPlaywrightRetriever:
    # Implements: FR-2
    # Workflow: reply_handling.md
    # Schema: evidence_record.md
    # API: research_api.md
    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http_client = http_client

    async def build_news_brief(self, *, lead_id: str, enrichment_brief: EnrichmentBrief) -> NewsBrief:
        urls = self._candidate_urls(enrichment_brief=enrichment_brief)
        if not urls:
            return NewsBrief(
                brief_id=f"news_{uuid4().hex[:10]}",
                lead_id=lead_id,
                company_id=enrichment_brief.company_id,
                found=False,
                confidence=0.0,
                risk_notes=["No website or Crunchbase URL available for public news lookup."],
            )

        errors: list[str] = []
        for url in urls:
            try:
                html = await self._fetch_html(url=url)
            except Exception as exc:  # Playwright browser installs are environment-dependent.
                errors.append(f"{url}: {exc}")
                continue
            if not html:
                continue
            title = self._title(html=html)
            snippet = self._snippet(html=html)
            if title or snippet:
                return NewsBrief(
                    brief_id=f"news_{uuid4().hex[:10]}",
                    lead_id=lead_id,
                    company_id=enrichment_brief.company_id,
                    found=True,
                    source_type=self._source_type(url=url),
                    title=title or "Recent public mention",
                    url=url,
                    published_at=self._published_at(html=html),
                    snippet=snippet,
                    confidence=0.72,
                    source_refs=[SourceRef(source_name="public_news_playwright", source_url=url)],
                )

        return NewsBrief(
            brief_id=f"news_{uuid4().hex[:10]}",
            lead_id=lead_id,
            company_id=enrichment_brief.company_id,
            found=False,
            confidence=0.2,
            error="; ".join(errors[:3]) or None,
            source_refs=[SourceRef(source_name="public_news_playwright", source_url=url) for url in urls[:3]],
            risk_notes=["No retrievable public filing or news mention found."],
        )

    def _candidate_urls(self, *, enrichment_brief: EnrichmentBrief) -> list[str]:
        website = enrichment_brief.firmographics.website
        crunchbase_url = enrichment_brief.firmographics.crunchbase_url
        urls: list[str] = []
        if website:
            base = website if "://" in website else f"https://{website}"
            urls.extend(
                [
                    urljoin(base.rstrip("/") + "/", "news"),
                    urljoin(base.rstrip("/") + "/", "press"),
                    urljoin(base.rstrip("/") + "/", "blog"),
                    urljoin(base.rstrip("/") + "/", "investors"),
                ]
            )
        if crunchbase_url:
            urls.append(crunchbase_url)
        return list(dict.fromkeys(urls))

    async def _fetch_html(self, *, url: str) -> str | None:
        if self._http_client is not None:
            response = await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
            return response.text if response.is_success else None
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - dependency is declared in requirements.
            raise RuntimeError("Playwright is not installed.") from exc
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=int(self._settings.http_timeout_seconds * 1000))
                return await page.content()
            finally:
                await browser.close()

    @staticmethod
    def _title(*, html: str) -> str | None:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return PublicNewsPlaywrightRetriever._clean(match.group(1))[:160]
        heading = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
        return PublicNewsPlaywrightRetriever._clean(heading.group(1))[:160] if heading else None

    @staticmethod
    def _snippet(*, html: str) -> str | None:
        meta = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if meta:
            return PublicNewsPlaywrightRetriever._clean(meta.group(1))[:300]
        text = PublicNewsPlaywrightRetriever._clean(re.sub(r"<[^>]+>", " ", html))
        return text[:300] if text else None

    @staticmethod
    def _published_at(*, html: str) -> str | None:
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", html)
        return match.group(1) if match else None

    @staticmethod
    def _source_type(*, url: str) -> str:
        lowered = url.lower()
        if "investor" in lowered or "sec.gov" in lowered or "filing" in lowered:
            return "filing"
        if "news" in lowered or "press" in lowered:
            return "news"
        if "blog" in lowered:
            return "company_post"
        return "unknown"

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
