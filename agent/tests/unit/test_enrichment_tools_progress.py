from __future__ import annotations

import asyncio

from agent.services.enrichment.merger import EnrichmentPipeline
from agent.services.enrichment.schemas import SignalSnapshot
from agent.tools.enrichment_tools import enrich_company


class _CrunchbaseStub:
    async def resolve_record(self, **kwargs):
        del kwargs
        return {"company_id": "comp_1"}

    async def collect(self, **kwargs):
        del kwargs
        return SignalSnapshot(summary={"funding_round": "Series A"}, confidence=0.9, source_refs=[])


class _JobsStub:
    async def collect(self, **kwargs):
        del kwargs
        return SignalSnapshot(
            summary={"engineering_role_count": 6, "ai_adjacent_role_count": 2, "role_titles": ["ML Engineer"]},
            confidence=0.8,
            source_refs=[],
        )


class _LayoffsStub:
    async def collect(self, **kwargs):
        del kwargs
        return SignalSnapshot(summary={"matched": False}, confidence=0.7, source_refs=[])


class _LeadershipStub:
    async def collect(self, **kwargs):
        del kwargs
        return SignalSnapshot(summary={"matched": False}, confidence=0.6, source_refs=[])


def test_enrich_company_reports_step_progress() -> None:
    events: list[tuple[str, str, str]] = []

    async def _cb(step: str, status: str, label: str) -> None:
        events.append((step, status, label))

    artifact = asyncio.run(
        enrich_company(
            company_id="comp_1",
            company_name="Acme",
            company_domain="acme.ai",
            crunchbase=_CrunchbaseStub(),
            jobs=_JobsStub(),
            layoffs=_LayoffsStub(),
            leadership=_LeadershipStub(),
            merger=EnrichmentPipeline(),
            progress_cb=_cb,
        )
    )

    assert artifact.company_id == "comp_1"
    expected_steps = [
        "enrichment.resolve_record",
        "enrichment.crunchbase",
        "enrichment.job_posts",
        "enrichment.layoffs",
        "enrichment.leadership",
        "enrichment.merge",
    ]
    running = [step for step, status, _ in events if status == "running"]
    done = [step for step, status, _ in events if status == "done"]
    assert running == expected_steps
    assert done == expected_steps
