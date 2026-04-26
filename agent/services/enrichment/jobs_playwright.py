"""Public job-page collector."""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from datetime import UTC, datetime
from typing import Any

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.schemas import SignalSnapshot, SourceRef

ROLE_PATTERN = re.compile(r"<[^>]+>|\s+")
LOGGER = logging.getLogger("agent.enrichment.jobs")
MAX_JOB_SOURCE_TIMEOUT_SECONDS = 8.0


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
        self._playwright_fallback_enabled = bool(settings.jobs_playwright_fallback_enabled)
        self._playwright_attempt_lock = asyncio.Lock()
        self._subprocess_supported: bool | None = None

    async def collect(self, *, company_domain: str, company_name: str | None = None) -> SignalSnapshot:
        slug = self._slug(company_name or company_domain)
        urls = [
            f"https://{company_domain}/careers",
            f"https://{company_domain}/jobs",
            f"https://builtin.com/company/{slug}/jobs",
            f"https://wellfound.com/company/{slug}/jobs",
        ]
        html_pages: list[tuple[str, str]] = []
        blocked_urls: list[str] = []
        per_request_timeout = min(float(self._settings.http_timeout_seconds), MAX_JOB_SOURCE_TIMEOUT_SECONDS)

        async def inspect_url(url: str, *, client: httpx.AsyncClient | None = None) -> tuple[str, str | None, bool]:
            allowed = await self._robots_allowed(url=url, timeout=per_request_timeout, client=client)
            if not allowed:
                return url, None, True
            html = await self._fetch_html(url=url, timeout=per_request_timeout, client=client)
            return url, html, False

        async def collect_with_client(client: httpx.AsyncClient | None) -> list[tuple[str, str | None, bool]]:
            tasks = [inspect_url(url, client=client) for url in urls]
            return await asyncio.gather(*tasks)

        if self._http_client is not None:
            results = await collect_with_client(self._http_client)
        else:
            async with httpx.AsyncClient(timeout=per_request_timeout) as client:
                results = await collect_with_client(client)

        for url, html, blocked in results:
            if blocked:
                blocked_urls.append(url)
                continue
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
                    "robots_blocked_urls": blocked_urls,
                    "window_days": 60,
                },
                confidence=0.35 if blocked_urls else 0.3,
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
                "robots_blocked_urls": blocked_urls,
                "window_days": 60,
            },
            confidence=confidence,
            source_refs=[SourceRef(source_name="jobs_playwright", source_url=url) for url, _ in html_pages],
        )

    async def _fetch_html(
        self,
        *,
        url: str,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> str | None:
        try:
            response = await self._get(url=url, timeout=timeout, client=client)
            if response.is_success and "text/html" in response.headers.get("Content-Type", "text/html"):
                return response.text
        except httpx.HTTPError:
            pass
        if self._http_client is None:
            return await self._fetch_html_with_playwright(url=url, timeout=timeout)
        return None

    async def _fetch_html_with_playwright(self, *, url: str, timeout: float | None = None) -> str | None:
        if not self._playwright_fallback_enabled:
            return None
        if not await self._subprocess_spawn_supported():
            self._playwright_fallback_enabled = False
            return None
        html: str | None = None
        async with self._playwright_attempt_lock:
            if not self._playwright_fallback_enabled:
                return None
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                self._playwright_fallback_enabled = False
                return None
            try:
                timeout_ms = int((timeout or self._settings.http_timeout_seconds) * 1000)
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True)
                    page = await browser.new_page(user_agent="TenaciousConversionEngineBot")
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    html = await page.content()
                    await browser.close()
            except Exception as exc:
                text = str(exc).lower()
                if "access is denied" in text or "permission" in text or "winerror 5" in text:
                    self._playwright_fallback_enabled = False
                    LOGGER.info("Playwright fallback disabled for jobs collector after permission failure.")
            if html is None:
                self._playwright_fallback_enabled = False
            return html

    async def _subprocess_spawn_supported(self) -> bool:
        if self._subprocess_supported is not None:
            return self._subprocess_supported
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "pass",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            self._subprocess_supported = True
        except Exception as exc:
            self._subprocess_supported = False
            LOGGER.info("Jobs collector subprocess checks failed; skipping Playwright fallback.", extra={"error": str(exc)})
        return self._subprocess_supported

    async def _robots_allowed(
        self,
        *,
        url: str,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            response = await self._get(url=robots_url, timeout=timeout, client=client)
        except httpx.HTTPError:
            return True
        if not response.is_success:
            return True
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch("TenaciousConversionEngineBot", url)

    async def _get(
        self,
        *,
        url: str,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> httpx.Response:
        request_timeout = timeout or self._settings.http_timeout_seconds
        active_client = client or self._http_client
        if active_client is not None:
            return await active_client.get(url, timeout=request_timeout)
        async with httpx.AsyncClient(timeout=request_timeout) as one_off_client:
            return await one_off_client.get(url)

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

    @staticmethod
    def _slug(value: str) -> str:
        parsed = urlparse(value if "://" in value else f"https://{value}")
        base = (parsed.netloc or parsed.path).removeprefix("www.").split(".")[0]
        return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "company"
