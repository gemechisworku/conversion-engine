"""HTTP-first page fetch with optional Playwright fallback (no link crawling)."""

from __future__ import annotations

import asyncio
import logging
import sys

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.web_research.html_extract import is_blocked_or_low_signal

LOGGER = logging.getLogger("agent.enrichment.web_research")


class PageFetcher:
    # Implements: FR-2
    # Workflow: reply_handling.md
    # API: research_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        use_playwright_fallback: bool = True,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._use_playwright_fallback = use_playwright_fallback
        self._playwright_fallback_enabled = bool(use_playwright_fallback)
        self._playwright_attempt_lock = asyncio.Lock()
        self._subprocess_supported: bool | None = None

    async def fetch_html(self, *, url: str, timeout: float) -> str | None:
        headers = {
            "User-Agent": "TenaciousConversionEngineBot/1.0 (+https://tenacious.example)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            if self._http_client is not None:
                response = await self._http_client.get(url, headers=headers, timeout=timeout)
            else:
                async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
                    response = await client.get(url)
        except httpx.HTTPError:
            return None
        if not response.is_success:
            return None
        if not response.text:
            return None
        return response.text

    async def fetch_html_with_fallback(self, *, url: str, timeout: float) -> str | None:
        html = await self.fetch_html(url=url, timeout=timeout)
        if html or self._http_client is not None or not self._use_playwright_fallback or not self._playwright_fallback_enabled:
            return html
        if not await self._subprocess_spawn_supported():
            self._playwright_fallback_enabled = False
            return None
        fallback_html: str | None = None
        async with self._playwright_attempt_lock:
            if not self._playwright_fallback_enabled:
                return None
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:  # pragma: no cover
                self._playwright_fallback_enabled = False
                raise RuntimeError("Playwright is not installed.") from exc
            try:
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True)
                    try:
                        context = await browser.new_context(ignore_https_errors=True)
                        page = await context.new_page()
                        await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
                        fallback_html = await page.content()
                    finally:
                        await browser.close()
            except Exception as exc:
                text = str(exc).lower()
                if "access is denied" in text or "permission" in text or "winerror 5" in text:
                    self._playwright_fallback_enabled = False
                    LOGGER.info("Playwright fallback disabled for web research after permission failure.")
            if fallback_html is None:
                self._playwright_fallback_enabled = False
            return fallback_html

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
            LOGGER.info("Web research subprocess checks failed; skipping Playwright fallback.", extra={"error": str(exc)})
        return self._subprocess_supported

    @staticmethod
    def page_usable(*, html: str) -> bool:
        if not html or len(html) < 80:
            return False
        return not is_blocked_or_low_signal(html)
