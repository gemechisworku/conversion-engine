"""Enrichment tool wrappers."""

from __future__ import annotations

from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.jobs_playwright import JobsPlaywrightCollector
from agent.services.enrichment.layoffs import LayoffsAdapter
from agent.services.enrichment.leadership import LeadershipChangeDetector
from agent.services.enrichment.merger import EnrichmentPipeline
from agent.services.enrichment.schemas import EnrichmentArtifact


async def enrich_company(
    *,
    company_id: str,
    company_name: str,
    company_domain: str,
    crunchbase: CrunchbaseAdapter,
    jobs: JobsPlaywrightCollector,
    layoffs: LayoffsAdapter,
    leadership: LeadershipChangeDetector,
    merger: EnrichmentPipeline,
) -> EnrichmentArtifact:
    crunchbase_signal = await crunchbase.collect(company_id=company_id, company_domain=company_domain)
    jobs_signal = await jobs.collect(company_domain=company_domain)
    layoffs_signal = await layoffs.collect(company_name=company_name)
    leadership_signal = await leadership.collect(company_name=company_name)
    return merger.merge(
        company_id=company_id,
        crunchbase=crunchbase_signal,
        job_posts=jobs_signal,
        layoffs=layoffs_signal,
        leadership_changes=leadership_signal,
    )

