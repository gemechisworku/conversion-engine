from __future__ import annotations

import asyncio

import httpx

from agent.config.settings import Settings
from agent.graphs.web_research_graph import build_research_runner


def _article_html() -> str:
    return (
        "<html><head><title>FinCo announces platform update</title>"
        '<meta name="description" content="FinCo shared a public product and compliance update.">'
        "</head><body><p>FinCo announced a public platform update for buyers in financial services.</p>"
        "</body></html>"
    )


def test_research_pipeline_search_fetch_extract_and_citations() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "lite.duckduckgo.com" in url:
            body = (
                '<html><a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample-news.test%2Fstory">'
                "FinCo story</a></html>"
            )
            return httpx.Response(200, text=body)
        if "wikipedia.org/w/api.php" in url:
            return httpx.Response(200, json={"query": {"search": []}})
        if "example-news.test" in url:
            return httpx.Response(200, text=_article_html(), headers={"Content-Type": "text/html"})
        return httpx.Response(404)

    settings = Settings(http_timeout_seconds=5.0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runner = build_research_runner(settings=settings, http_client=client)
    result = asyncio.run(
        runner.run(user_query="FinCo company news", max_search_results=6, mode="news", seed_urls=[])
    )
    asyncio.run(client.aclose())

    assert result.ranked_pages, "expected at least one extracted page"
    assert "example-news.test" in result.source_urls[0]
    assert "Source:" in result.synthesis and result.source_urls[0] in result.synthesis


def test_research_pipeline_skips_failed_pages_without_crash() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "lite.duckduckgo.com" in url:
            links = (
                '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fbad.test%2Fmissing">bad</a>'
                '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fgood.test%2Fok">good</a>'
            )
            return httpx.Response(200, text=f"<html>{links}</html>")
        if "wikipedia.org/w/api.php" in url:
            return httpx.Response(200, json={"query": {"search": []}})
        if "bad.test" in url:
            return httpx.Response(500)
        if "good.test" in url:
            return httpx.Response(200, text=_article_html())
        return httpx.Response(404)

    settings = Settings(http_timeout_seconds=5.0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runner = build_research_runner(settings=settings, http_client=client)
    result = asyncio.run(runner.run(user_query="FinCo financial news", max_search_results=6))
    asyncio.run(client.aclose())

    assert result.ranked_pages
    assert "good.test" in result.source_urls[0]
    assert any("bad.test" in c for c in calls)


def test_answer_includes_source_urls_when_ranked_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "lite.duckduckgo.com" in url:
            return httpx.Response(200, text="<html></html>")
        if "wikipedia.org/w/api.php" in url:
            return httpx.Response(200, json={"query": {"search": []}})
        return httpx.Response(404)

    settings = Settings(http_timeout_seconds=5.0)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runner = build_research_runner(settings=settings, http_client=client)
    result = asyncio.run(runner.run(user_query="obscure xyzabc123 noresults", max_search_results=5))
    asyncio.run(client.aclose())

    assert not result.source_urls or not result.ranked_pages
    assert "No verifiable" in result.synthesis or result.errors
