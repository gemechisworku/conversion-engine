from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import httpx

from agent.config.settings import Settings
from agent.graphs.lead_intake_langgraph import LeadIntakeGraphDeps, compile_lead_intake_graph
from agent.graphs.state import LeadGraphState
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.enrichment.competitor_gap import CompetitorGapAnalyst
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.jobs_playwright import JobsPlaywrightCollector
from agent.services.enrichment.layoffs import LayoffsAdapter
from agent.services.enrichment.leadership import LeadershipChangeDetector
from agent.services.enrichment.merger import EnrichmentPipeline
from agent.services.enrichment.news_playwright import PublicNewsPlaywrightRetriever
from agent.services.enrichment.schemas import EnrichmentArtifact

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "enrichment"


def _deps() -> LeadIntakeGraphDeps:
    settings = Settings(
        challenge_mode=False,
        sink_routing_enabled=True,
        state_db_path=f"outputs/test_lead_lg_{uuid4().hex}.db",
        act2_evidence_dir="outputs/test_lead_lg_evidence",
        crunchbase_dataset_path=str(FIXTURE_DIR / "crunchbase_sample.json"),
        layoffs_csv_path=str(FIXTURE_DIR / "layoffs_sample.csv"),
        leadership_feed_url=str(FIXTURE_DIR / "leadership_sample.json"),
    )
    repo = SQLiteStateRepository(db_path=settings.state_db_path)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    crunchbase = CrunchbaseAdapter(settings=settings)
    services = {
        "settings": settings,
        "crunchbase": crunchbase,
        "jobs": JobsPlaywrightCollector(settings=settings, http_client=http_client),
        "layoffs": LayoffsAdapter(settings=settings),
        "leadership": LeadershipChangeDetector(settings=settings),
        "merger": EnrichmentPipeline(),
        "competitor_gap": CompetitorGapAnalyst(settings=settings),
        "llm": None,
        "news": PublicNewsPlaywrightRetriever(settings=settings, http_client=http_client),
    }
    return LeadIntakeGraphDeps(hubspot=None, enrichment_services=services, state_repo=repo)


def test_lead_intake_graph_runs_enrich_then_crm_skip_without_hubspot() -> None:
    deps = _deps()
    graph = compile_lead_intake_graph(deps)
    lead_state = LeadGraphState(lead_id="lead_x", company_id="comp_1", current_stage="enriching")
    out = asyncio.run(
        graph.ainvoke(
            {
                "lead_id": "lead_x",
                "company_id": "comp_1",
                "company_name": "Acme AI",
                "company_domain": "acme.ai",
                "trace_id": "trace_t",
                "idempotency_key": "idem_lg",
                "lead_state": lead_state.model_dump(mode="json"),
                "errors": [],
            }
        )
    )
    assert out.get("crm_synced") is False
    enriched = LeadGraphState.model_validate(out["enriched_state"])
    assert enriched.current_stage == "brief_ready"
    EnrichmentArtifact.model_validate(out["artifact"])


def test_lead_intake_graph_produces_artifact_with_signals() -> None:
    deps = _deps()
    graph = compile_lead_intake_graph(deps)
    lead_state = LeadGraphState(lead_id="lead_y", company_id="comp_2", current_stage="enriching")
    out = asyncio.run(
        graph.ainvoke(
            {
                "lead_id": "lead_y",
                "company_id": "comp_2",
                "company_name": "Acme AI",
                "company_domain": "acme.ai",
                "trace_id": "trace_t2",
                "idempotency_key": "idem_lg2",
                "lead_state": lead_state.model_dump(mode="json"),
                "errors": [],
            }
        )
    )
    art = EnrichmentArtifact.model_validate(out["artifact"])
    assert "crunchbase" in art.signals
