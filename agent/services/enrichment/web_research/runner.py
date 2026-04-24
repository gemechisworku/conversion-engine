"""LangGraph wiring: search → fetch/extract → summarize+rank → answer."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from langgraph.graph import END, StateGraph

from agent.config.settings import Settings
from agent.services.enrichment.web_research.fetch_page import PageFetcher
from agent.services.enrichment.web_research.html_extract import extract_main_text, extract_meta_description, extract_title
from agent.services.enrichment.web_research.providers import (
    SearchProvider,
    aggregate_search_hits,
    build_default_search_stack,
    default_http_headers,
)
from agent.services.observability.events import log_processing_step
from agent.services.enrichment.web_research.types import (
    ControlledResearchResult,
    ExtractedPage,
    RankedPage,
    ResearchGraphState,
    SearchHit,
)


@dataclass
class ResearchDeps:
    settings: Settings
    http_client: httpx.AsyncClient | None
    search_providers: list[SearchProvider]
    page_fetcher: PageFetcher


def _query_tokens(query: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]{2,}", query.lower()) if len(t) >= 2]


def _relevance_score(*, query: str, text: str) -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return 0.35
    lowered = text.lower()
    hits = sum(1 for t in tokens if t in lowered)
    return min(1.0, hits / len(tokens))


def _brief_summary(text: str, *, max_len: int = 360) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _dedupe_ranked(pages: list[RankedPage]) -> list[RankedPage]:
    seen: set[str] = set()
    out: list[RankedPage] = []
    for page in sorted(pages, key=lambda p: p.relevance, reverse=True):
        key = page.url.split("#", 1)[0].rstrip("/").lower()
        if key in seen:
            continue
        sig = page.body_excerpt[:180].lower()
        if any(existing.body_excerpt[:180].lower() == sig for existing in out):
            continue
        seen.add(key)
        out.append(page)
    return out


def build_research_runner(*, settings: Settings, http_client: httpx.AsyncClient | None = None) -> ControlledWebResearchRunner:
    fetcher = PageFetcher(settings=settings, http_client=http_client, use_playwright_fallback=http_client is None)
    deps = ResearchDeps(
        settings=settings,
        http_client=http_client,
        search_providers=build_default_search_stack(settings),
        page_fetcher=fetcher,
    )
    return ControlledWebResearchRunner(deps=deps)


class ControlledWebResearchRunner:
    """Controlled AI research pipeline (single-hop from search results only)."""

    def __init__(self, *, deps: ResearchDeps) -> None:
        self._deps = deps
        self._graph = _compile_graph(deps)

    async def run(
        self,
        *,
        user_query: str,
        max_search_results: int = 8,
        mode: Literal["news", "competitor", "generic"] = "generic",
        seed_urls: list[str] | None = None,
    ) -> ControlledResearchResult:
        max_results = max(5, min(10, max_search_results))
        timeout = min(20.0, float(self._deps.settings.http_timeout_seconds))
        initial: ResearchGraphState = {
            "user_query": user_query,
            "max_search_results": max_results,
            "max_depth": 1,
            "per_page_timeout_seconds": timeout,
            "mode": mode,
            "errors": [],
            "seed_urls": list(seed_urls or []),
        }
        log_processing_step(
            component="graphs.web_research",
            step="pipeline.start",
            message="Running web research LangGraph (search → fetch → rank → answer)",
            mode=mode,
            max_results=max_results,
            timeout_seconds=timeout,
            seed_url_count=len(initial.get("seed_urls") or []),
            query_preview=user_query[:120],
        )
        final: ResearchGraphState = await self._graph.ainvoke(initial)
        ranked = [RankedPage.model_validate(row) for row in final.get("ranked_pages") or []]
        err_list = list(final.get("errors") or [])
        log_processing_step(
            component="graphs.web_research",
            step="pipeline.done",
            message="Web research graph finished",
            mode=mode,
            ranked_pages=len(ranked),
            source_urls=len(final.get("source_urls") or []),
            error_events=len(err_list),
            level=logging.WARNING if not ranked and err_list else logging.INFO,
        )
        return ControlledResearchResult(
            synthesis=final.get("synthesis") or "",
            source_urls=list(final.get("source_urls") or []),
            ranked_pages=ranked,
            errors=list(final.get("errors") or []),
        )


def _compile_graph(deps: ResearchDeps):
    graph: StateGraph = StateGraph(ResearchGraphState)

    async def search_node(state: ResearchGraphState) -> dict[str, Any]:
        query = state.get("user_query") or ""
        max_results = int(state.get("max_search_results") or 8)
        timeout = float(state.get("per_page_timeout_seconds") or 15.0)
        err_out: list[str] = []
        if not query.strip():
            err_out.append("search:empty_query")
            return {"search_hits": [], "errors": err_out}
        client = deps.http_client or httpx.AsyncClient(timeout=timeout, headers=default_http_headers())
        own_client = deps.http_client is None
        try:
            hits, errs = await aggregate_search_hits(
                providers=deps.search_providers,
                query=query,
                max_results=max_results,
                http_client=client,
                timeout=timeout,
            )
        finally:
            if own_client:
                await client.aclose()
        seed_hits: list[SearchHit] = []
        seen: set[str] = set()
        for url in state.get("seed_urls") or []:
            key = url.split("#", 1)[0].rstrip("/").lower()
            if not url.startswith("http") or key in seen:
                continue
            seen.add(key)
            seed_hits.append(SearchHit(title=None, url=url, snippet=None, provider="seed_company_page"))
        for h in hits:
            key = h.url.split("#", 1)[0].rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            seed_hits.append(h)
        merged = seed_hits[:max_results]
        log_processing_step(
            component="graphs.web_research",
            step="search",
            message="Search + seed URLs merged",
            hit_count=len(merged),
            query_preview=(query[:100] + "…") if len(query) > 100 else query,
        )
        return {"search_hits": [h.model_dump(mode="json") for h in merged], "errors": [*errs, *err_out]}

    async def fetch_extract_node(state: ResearchGraphState) -> dict[str, Any]:
        raw_hits = state.get("search_hits") or []
        timeout = float(state.get("per_page_timeout_seconds") or 15.0)
        extracted: list[dict[str, Any]] = []
        err_out: list[str] = []
        for row in raw_hits:
            hit = SearchHit.model_validate(row)
            url = hit.url
            try:
                html = await deps.page_fetcher.fetch_html_with_fallback(url=url, timeout=timeout)
            except Exception as exc:
                err_out.append(f"fetch:{url}:{exc}")
                extracted.append(
                    ExtractedPage(url=url, title=hit.title, text="", metadata={"provider": hit.provider}, fetch_error=str(exc)).model_dump(
                        mode="json"
                    )
                )
                continue
            if not html or not PageFetcher.page_usable(html=html):
                err_out.append(f"fetch:empty_or_blocked:{url}")
                extracted.append(
                    ExtractedPage(
                        url=url,
                        title=hit.title,
                        text="",
                        metadata={"provider": hit.provider},
                        fetch_error="empty_or_blocked",
                    ).model_dump(mode="json")
                )
                continue
            title = extract_title(html) or hit.title
            meta = extract_meta_description(html)
            body = extract_main_text(html)
            combined_preview = f"{meta}\n\n{body}" if meta else body
            if len(combined_preview.strip()) < 100:
                err_out.append(f"extract:low_signal:{url}")
                extracted.append(
                    ExtractedPage(
                        url=url,
                        title=title,
                        text="",
                        metadata={"provider": hit.provider, "meta_description": meta},
                        fetch_error="low_signal",
                    ).model_dump(mode="json")
                )
                continue
            excerpt = combined_preview[:8000]
            extracted.append(
                ExtractedPage(
                    url=url,
                    title=title,
                    text=excerpt[:8000],
                    metadata={"provider": hit.provider, "meta_description": meta},
                    fetch_error=None,
                ).model_dump(mode="json")
            )
        if not any(not row.get("fetch_error") for row in extracted):
            err_out.append("fetch:no_usable_pages")
        usable = sum(1 for row in extracted if not row.get("fetch_error"))
        log_processing_step(
            component="graphs.web_research",
            step="fetch_extract",
            message="Fetched and extracted candidate pages",
            urls_attempted=len(raw_hits),
            pages_usable=usable,
        )
        return {"extracted_pages": extracted, "errors": err_out}

    async def summarize_rank_node(state: ResearchGraphState) -> dict[str, Any]:
        query = state.get("user_query") or ""
        pages = [ExtractedPage.model_validate(row) for row in state.get("extracted_pages") or []]
        err_out: list[str] = []
        ranked: list[RankedPage] = []
        for page in pages:
            if page.fetch_error or not page.text.strip():
                continue
            summary = _brief_summary(page.text)
            rel = _relevance_score(query=query, text=page.text)
            if rel < 0.02 and len(page.text) < 200:
                continue
            ranked.append(
                RankedPage(
                    url=page.url,
                    title=page.title,
                    summary=summary,
                    relevance=round(rel, 3),
                    body_excerpt=page.text[:500],
                )
            )
        ranked = _dedupe_ranked(ranked)[:10]
        if not ranked:
            err_out.append("rank:no_pages")
        log_processing_step(
            component="graphs.web_research",
            step="summarize_rank",
            message="Ranked pages for answer node",
            ranked_count=len(ranked),
        )
        return {"ranked_pages": [r.model_dump(mode="json") for r in ranked], "errors": err_out}

    async def answer_node(state: ResearchGraphState) -> dict[str, Any]:
        query = state.get("user_query") or ""
        ranked = [RankedPage.model_validate(row) for row in state.get("ranked_pages") or []]
        err_out: list[str] = []
        if not ranked:
            log_processing_step(
                component="graphs.web_research",
                step="answer",
                message="No ranked pages; emitting empty synthesis",
                query_preview=(query[:80] + "…") if len(query) > 80 else query,
                level=logging.WARNING,
            )
            return {
                "synthesis": f"No verifiable public pages could be synthesized for query: {query!r}.",
                "source_urls": [],
                "errors": err_out,
            }
        lines: list[str] = [
            "Findings are grounded only in the fetched pages below. Each bullet cites its source URL.",
            "",
        ]
        urls: list[str] = []
        for idx, page in enumerate(ranked[:8], start=1):
            lines.append(f"{idx}. ({page.title or 'Untitled'}) {page.summary}")
            lines.append(f"   Source: {page.url}")
            lines.append("")
            urls.append(page.url)
        synthesis = "\n".join(lines).strip()
        log_processing_step(
            component="graphs.web_research",
            step="answer",
            message="Built grounded synthesis with citations",
            citation_count=len(urls),
            synthesis_chars=len(synthesis),
        )
        return {"synthesis": synthesis, "source_urls": urls, "errors": err_out}

    graph.add_node("search", search_node)
    graph.add_node("fetch_extract", fetch_extract_node)
    graph.add_node("summarize_rank", summarize_rank_node)
    graph.add_node("answer", answer_node)
    graph.set_entry_point("search")
    graph.add_edge("search", "fetch_extract")
    graph.add_edge("fetch_extract", "summarize_rank")
    graph.add_edge("summarize_rank", "answer")
    graph.add_edge("answer", END)
    return graph.compile()
