"""Playwright-backed public news/filing retrieval via controlled LangGraph research."""

from __future__ import annotations

import re
from urllib.parse import urljoin
from uuid import uuid4

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.web_research.runner import ControlledWebResearchRunner, build_research_runner
from agent.services.enrichment.schemas import EnrichmentBrief, NewsBrief, SourceRef
from agent.services.enrichment.web_research.types import ControlledResearchResult


def _failure_risk_notes(research: ControlledResearchResult) -> list[str]:
    notes = ["Controlled web research did not yield ranked pages; verify before making strong claims."]
    if research.synthesis:
        notes.append(research.synthesis[:500])
    return notes


class PublicNewsPlaywrightRetriever:
    # Implements: FR-2
    # Workflow: reply_handling.md
    # Schema: evidence_record.md
    # API: research_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        web_research: ControlledWebResearchRunner | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._web_research = web_research or build_research_runner(settings=settings, http_client=http_client)

    async def build_news_brief(self, *, lead_id: str, enrichment_brief: EnrichmentBrief) -> NewsBrief:
        company_name = enrichment_brief.firmographics.company_name
        if not company_name:
            return NewsBrief(
                brief_id=f"news_{uuid4().hex[:10]}",
                lead_id=lead_id,
                company_id=enrichment_brief.company_id,
                found=False,
                confidence=0.0,
                error="search_skipped:missing_company_name",
                risk_notes=["No company name available for controlled web research."],
            )

        domain = enrichment_brief.firmographics.domain
        aliases = self._company_aliases(company_name=company_name, domain=domain)
        base_terms = [company_name, *aliases[:2]]
        query = " OR ".join(f'"{term}" news OR press release' for term in base_terms[:3])
        if domain:
            query = f"({query}) ({domain})"

        seed_urls = self._candidate_urls(enrichment_brief=enrichment_brief)
        research = await self._web_research.run(
            user_query=query,
            max_search_results=8,
            mode="news",
            seed_urls=seed_urls[:4],
        )

        source_refs = [
            SourceRef(source_name="controlled_web_research", source_url=url) for url in research.source_urls[:10]
        ]
        if not research.ranked_pages:
            return NewsBrief(
                brief_id=f"news_{uuid4().hex[:10]}",
                lead_id=lead_id,
                company_id=enrichment_brief.company_id,
                found=False,
                confidence=0.15,
                source_refs=source_refs,
                error="; ".join((research.errors or [])[:4]) or "research:no_ranked_pages",
                risk_notes=_failure_risk_notes(research),
            )

        top = research.ranked_pages[0]
        confidence = min(0.88, 0.58 + 0.06 * min(len(research.ranked_pages), 5))
        return NewsBrief(
            brief_id=f"news_{uuid4().hex[:10]}",
            lead_id=lead_id,
            company_id=enrichment_brief.company_id,
            found=True,
            source_type=self._source_type(url=top.url),
            title=top.title or "Recent public mention",
            url=top.url,
            published_at=None,
            snippet=top.summary[:400] if top.summary else None,
            confidence=confidence,
            source_refs=source_refs or [SourceRef(source_name="controlled_web_research", source_url=top.url)],
            risk_notes=[
                "News brief synthesized only from fetched pages in the research graph; citations are required for outreach claims.",
                (
                    f"Synthesis excerpt: {research.synthesis[:420]}…"
                    if len(research.synthesis) > 420
                    else f"Synthesis: {research.synthesis}"
                ),
            ],
        )

    def _candidate_urls(self, *, enrichment_brief: EnrichmentBrief) -> list[str]:
        website = enrichment_brief.firmographics.website
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
        return list(dict.fromkeys(urls))

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

    @staticmethod
    def _company_aliases(*, company_name: str, domain: str | None) -> list[str]:
        blocked = {"inc", "inc.", "llc", "ltd", "corp", "corp.", "corporation", "company", "co", "capital"}
        parts = [token for token in re.split(r"[^a-z0-9]+", company_name.lower()) if token and token not in blocked]
        aliases: list[str] = []
        if len(parts) >= 2:
            aliases.append(" ".join(parts[:2]))
            aliases.append(" ".join(parts[:3]))
        if parts:
            aliases.append(parts[0])
        if domain:
            root = domain.lower().split(".")[0].replace("-", " ").strip()
            if root:
                aliases.append(root)
        deduped: list[str] = []
        for value in aliases:
            if value and value not in deduped:
                deduped.append(value)
        return deduped
