"""Pluggable search providers (SerpAPI, DuckDuckGo lite, Wikipedia)."""

from __future__ import annotations

import re
from typing import Protocol
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.web_research.types import SearchHit


class SearchProvider(Protocol):
    name: str

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        http_client: httpx.AsyncClient,
        timeout: float,
    ) -> list[SearchHit]:
        """Return up to max_results hits; empty on failure."""


def default_http_headers() -> dict[str, str]:
    return {
        "User-Agent": "TenaciousConversionEngineBot/1.0 (+https://tenacious.example)",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }


def unwrap_ddg_redirect(href: str) -> str | None:
    if "uddg=" not in href:
        return None
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    raw = (qs.get("uddg") or [None])[0]
    if not raw:
        return None
    return unquote(raw)


class SerpAPIProvider:
    name = "serpapi_google"

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key.strip()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        http_client: httpx.AsyncClient,
        timeout: float,
    ) -> list[SearchHit]:
        if not self.configured:
            return []
        params = {"engine": "google", "q": query, "api_key": self._api_key, "num": str(min(max_results, 10))}
        try:
            response = await http_client.get(
                "https://serpapi.com/search.json",
                params=params,
                headers=default_http_headers(),
                timeout=timeout,
            )
        except httpx.HTTPError:
            return []
        if not response.is_success:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        organic = payload.get("organic_results") or []
        hits: list[SearchHit] = []
        for row in organic[:max_results]:
            link = row.get("link")
            if not link or not str(link).startswith("http"):
                continue
            hits.append(
                SearchHit(
                    title=row.get("title"),
                    url=str(link),
                    snippet=row.get("snippet"),
                    provider=self.name,
                )
            )
        return hits


class DuckDuckGoLiteProvider:
    name = "duckduckgo_lite"

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        http_client: httpx.AsyncClient,
        timeout: float,
    ) -> list[SearchHit]:
        try:
            response = await http_client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers=default_http_headers(),
                timeout=timeout,
            )
        except httpx.HTTPError:
            return []
        if not response.is_success:
            return []
        text = response.text
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for match in re.finditer(r'href="([^"]+uddg=[^"]+)"', text, flags=re.IGNORECASE):
            raw_url = unwrap_ddg_redirect(match.group(1))
            if not raw_url or not raw_url.startswith("http"):
                continue
            if "duckduckgo.com" in raw_url.lower():
                continue
            if raw_url in seen:
                continue
            seen.add(raw_url)
            title_match = re.search(
                r"<a[^>]+href=[\"']" + re.escape(match.group(1)) + r"[\"'][^>]*>([^<]+)</a>",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            title = re.sub(r"<[^>]+>", " ", title_match.group(1)).strip()[:200] if title_match else None
            hits.append(SearchHit(title=title or None, url=raw_url, snippet=None, provider=self.name))
            if len(hits) >= max_results:
                break
        return hits


class WikipediaSearchProvider:
    name = "wikipedia_api"

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        http_client: httpx.AsyncClient,
        timeout: float,
    ) -> list[SearchHit]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": str(min(max_results, 10)),
        }
        try:
            response = await http_client.get(
                "https://en.wikipedia.org/w/api.php",
                params=params,
                headers=default_http_headers(),
                timeout=timeout,
            )
        except httpx.HTTPError:
            return []
        if not response.is_success:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        rows = (payload.get("query") or {}).get("search") or []
        hits: list[SearchHit] = []
        for row in rows[:max_results]:
            title = row.get("title")
            if not title:
                continue
            slug = str(title).replace(" ", "_")
            url = "https://en.wikipedia.org/wiki/" + quote(slug, safe="/():_%")
            snippet = row.get("snippet")
            if isinstance(snippet, str):
                snippet = re.sub(r"<[^>]+>", " ", snippet).strip()[:300] or None
            hits.append(SearchHit(title=str(title), url=url, snippet=snippet, provider=self.name))
        return hits


def build_default_search_stack(settings: Settings) -> list[SearchProvider]:
    """SerpAPI first when configured; always include DDG lite and Wikipedia as fallbacks."""
    stack: list[SearchProvider] = []
    serp = SerpAPIProvider(api_key=settings.serpapi_api_key)
    if serp.configured:
        stack.append(serp)
    stack.append(DuckDuckGoLiteProvider())
    stack.append(WikipediaSearchProvider())
    return stack


async def aggregate_search_hits(
    *,
    providers: list[SearchProvider],
    query: str,
    max_results: int,
    http_client: httpx.AsyncClient,
    timeout: float,
) -> tuple[list[SearchHit], list[str]]:
    merged: list[SearchHit] = []
    seen_urls: set[str] = set()
    errors: list[str] = []
    for provider in providers:
        try:
            batch = await provider.search(
                query=query, max_results=max_results, http_client=http_client, timeout=timeout
            )
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"{getattr(provider, 'name', 'search')}: {exc}")
            continue
        for hit in batch:
            key = hit.url.split("#", 1)[0].rstrip("/").lower()
            if key in seen_urls:
                continue
            seen_urls.add(key)
            merged.append(hit)
            if len(merged) >= max_results:
                return merged, errors
    if not merged:
        errors.append("search:no_hits")
    return merged, errors
