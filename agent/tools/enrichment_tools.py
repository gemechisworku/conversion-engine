"""Enrichment tool wrappers."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from agent.config.settings import Settings
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.jobs_playwright import JobsPlaywrightCollector
from agent.services.enrichment.layoffs import LayoffsAdapter
from agent.services.enrichment.leadership import LeadershipChangeDetector
from agent.services.enrichment.merger import EnrichmentPipeline
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.services.observability.langfuse_llm import langfuse_workflow_span

EnrichmentProgressCallback = Callable[[str, str, str], Awaitable[None] | None]


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
    progress_cb: EnrichmentProgressCallback | None = None,
) -> EnrichmentArtifact:
    async def _notify(step: str, status: str, label: str) -> None:
        if progress_cb is None:
            return
        maybe = progress_cb(step, status, label)
        if inspect.isawaitable(maybe):
            await maybe

    async def _step(step: str, span_name: str, label: str, coro):
        await _notify(step, "running", label)
        if lf_settings is not None and lf_trace_id:
            with langfuse_workflow_span(
                lf_settings,
                trace_id=lf_trace_id,
                lead_id=lf_lead_id,
                name=span_name,
            ):
                try:
                    result = await coro
                except Exception:
                    await _notify(step, "failed", label)
                    raise
        else:
            try:
                result = await coro
            except Exception:
                await _notify(step, "failed", label)
                raise
        await _notify(step, "done", label)
        return result

    crunchbase_row = await _step(
        "enrichment.resolve_record",
        "enrichment.crunchbase.resolve",
        "Resolve source company record",
        crunchbase.resolve_record(
            company_id=company_id,
            company_name=company_name,
            company_domain=company_domain,
        ),
    )
    crunchbase_signal = await _step(
        "enrichment.crunchbase",
        "enrichment.crunchbase.collect",
        "Collect Crunchbase profile",
        crunchbase.collect(company_id=company_id, company_domain=company_domain),
    )
    jobs_signal = await _step(
        "enrichment.job_posts",
        "enrichment.jobs.collect",
        "Collect public job-post signals",
        jobs.collect(company_domain=company_domain, company_name=company_name),
    )
    layoffs_signal = await _step(
        "enrichment.layoffs",
        "enrichment.layoffs.collect",
        "Collect layoff signals",
        layoffs.collect(company_name=company_name, crunchbase_row=crunchbase_row),
    )
    leadership_signal = await _step(
        "enrichment.leadership",
        "enrichment.leadership.collect",
        "Collect leadership-change signals",
        leadership.collect(company_name=company_name, crunchbase_row=crunchbase_row),
    )
    await _notify("enrichment.merge", "running", "Merge enrichment sources")
    merged = merger.merge(
        company_id=company_id,
        crunchbase=crunchbase_signal,
        job_posts=jobs_signal,
        layoffs=layoffs_signal,
        leadership_changes=leadership_signal,
    )
    await _notify("enrichment.merge", "done", "Merge enrichment sources")
    return merged
