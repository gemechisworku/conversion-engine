"""HTTP-first page fetch with optional Playwright fallback (no link crawling)."""

from __future__ import annotations

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.web_research.html_extract import is_blocked_or_low_signal


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
        if html or self._http_client is not None or not self._use_playwright_fallback:
            return html
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Playwright is not installed.") from exc
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(ignore_https_errors=True)
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
                return await page.content()
            finally:
                await browser.close()

    @staticmethod
    def page_usable(*, html: str) -> bool:
        if not html or len(html) < 80:
            return False
        return not is_blocked_or_low_signal(html)
