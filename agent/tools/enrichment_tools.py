"""Enrichment tool wrappers."""

from __future__ import annotations

from agent.config.settings import Settings
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.jobs_playwright import JobsPlaywrightCollector
from agent.services.enrichment.layoffs import LayoffsAdapter
from agent.services.enrichment.leadership import LeadershipChangeDetector
from agent.services.enrichment.merger import EnrichmentPipeline
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.services.observability.langfuse_llm import langfuse_workflow_span


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
    lf_settings: Settings | None = None,
    lf_trace_id: str | None = None,
    lf_lead_id: str | None = None,
) -> EnrichmentArtifact:
    async def _step(name: str, coro):
        if lf_settings is not None and lf_trace_id:
            with langfuse_workflow_span(
                lf_settings,
                trace_id=lf_trace_id,
                lead_id=lf_lead_id,
                name=name,
            ):
                return await coro
        return await coro

    crunchbase_row = await _step(
        "enrichment.crunchbase.resolve",
        crunchbase.resolve_record(
            company_id=company_id,
            company_name=company_name,
            company_domain=company_domain,
        ),
    )
    crunchbase_signal = await _step(
        "enrichment.crunchbase.collect",
        crunchbase.collect(company_id=company_id, company_domain=company_domain),
    )
    jobs_signal = await _step(
        "enrichment.jobs.collect",
        jobs.collect(company_domain=company_domain, company_name=company_name),
    )
    layoffs_signal = await _step(
        "enrichment.layoffs.collect",
        layoffs.collect(company_name=company_name, crunchbase_row=crunchbase_row),
    )
    leadership_signal = await _step(
        "enrichment.leadership.collect",
        leadership.collect(company_name=company_name, crunchbase_row=crunchbase_row),
    )
    return merger.merge(
        company_id=company_id,
        crunchbase=crunchbase_signal,
        job_posts=jobs_signal,
        layoffs=layoffs_signal,
        leadership_changes=leadership_signal,
    )
