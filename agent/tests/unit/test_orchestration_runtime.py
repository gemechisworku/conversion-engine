from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import httpx

from agent.config.settings import Settings
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.enrichment.act2_pipeline import ActIIEnrichmentPipeline
from agent.services.enrichment.cfpb import CFPBComplaintAdapter
from agent.services.enrichment.competitor_gap import CompetitorGapAnalyst
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.jobs_playwright import JobsPlaywrightCollector
from agent.services.enrichment.layoffs import LayoffsAdapter
from agent.services.enrichment.leadership import LeadershipChangeDetector
from agent.services.enrichment.merger import EnrichmentPipeline
from agent.services.enrichment.news_playwright import PublicNewsPlaywrightRetriever
from agent.services.orchestration.runtime import OrchestrationRuntime
from agent.services.orchestration.schemas import LeadAdvanceRequest, LeadProcessRequest, LeadReplyRequest


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "enrichment"


def _settings() -> Settings:
    return Settings(
        challenge_mode=False,
        sink_routing_enabled=True,
        state_db_path=f"outputs/test_runtime_state_{uuid4().hex}.db",
        act2_evidence_dir="outputs/test_act2_evidence",
        crunchbase_dataset_path=str(FIXTURE_DIR / "crunchbase_sample.json"),
        layoffs_csv_path=str(FIXTURE_DIR / "layoffs_sample.csv"),
        leadership_feed_url=str(FIXTURE_DIR / "leadership_sample.json"),
    )


def _runtime() -> OrchestrationRuntime:
    settings = _settings()
    repo = SQLiteStateRepository(db_path=settings.state_db_path)
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    crunchbase = CrunchbaseAdapter(settings=settings)
    cfpb = CFPBComplaintAdapter(settings=settings, http_client=http_client)
    news = PublicNewsPlaywrightRetriever(settings=settings, http_client=http_client)
    services = {
        "crunchbase": crunchbase,
        "jobs": JobsPlaywrightCollector(settings=settings, http_client=http_client),
        "layoffs": LayoffsAdapter(settings=settings),
        "leadership": LeadershipChangeDetector(settings=settings),
        "merger": EnrichmentPipeline(),
        "competitor_gap": CompetitorGapAnalyst(settings=settings),
        "cfpb": cfpb,
        "news": news,
        "act2_pipeline": ActIIEnrichmentPipeline(
            settings=settings,
            crunchbase=crunchbase,
            cfpb=cfpb,
            news=news,
        ),
    }
    return OrchestrationRuntime(
        settings=settings,
        state_repo=repo,
        enrichment_services=services,
        hubspot_service=None,
    )


def test_process_lead_generates_brief_ready_state() -> None:
    runtime = _runtime()
    response = asyncio.run(
        runtime.process_lead(
            LeadProcessRequest(
                idempotency_key="idem_1",
                company_id="comp_123",
                metadata={"company_name": "Acme AI", "company_domain": "acme.ai"},
            )
        )
    )
    assert response.status == "accepted"
    assert response.data["state"] == "brief_ready"
    state = runtime.get_state(lead_id=response.data["lead_id"])
    assert state.status == "success"
    assert state.data["state"] == "brief_ready"


def test_reply_updates_next_action() -> None:
    runtime = _runtime()
    processed = asyncio.run(
        runtime.process_lead(
            LeadProcessRequest(
                idempotency_key="idem_2",
                company_id="comp_234",
                metadata={"company_name": "Acme AI", "company_domain": "acme.ai"},
            )
        )
    )
    lead_id = processed.data["lead_id"]
    transitions = [
        ("brief_ready", "drafting"),
        ("drafting", "in_review"),
        ("in_review", "queued_to_send"),
        ("queued_to_send", "awaiting_reply"),
    ]
    for idx, (from_state, to_state) in enumerate(transitions, start=1):
        advance = asyncio.run(
            runtime.advance_state(
                LeadAdvanceRequest(
                    idempotency_key=f"idem_reply_adv_{idx}",
                    lead_id=lead_id,
                    from_state=from_state,
                    to_state=to_state,
                    reason="test setup",
                )
            )
        )
        assert advance.status == "success"
    reply = asyncio.run(
        runtime.handle_reply(
            LeadReplyRequest(
                idempotency_key="idem_reply_1",
                lead_id=lead_id,
                channel="email",
                message_id="msg_1",
                content="Can you share available times next week?",
                from_email="buyer@acme.ai",
            )
        )
    )
    assert reply.status == "accepted"
    assert reply.data["next_action"] == "schedule"
    assert runtime._state_repo.get_act2_briefs(lead_id=lead_id) is not None


def test_invalid_advance_transition_rejected() -> None:
    runtime = _runtime()
    processed = asyncio.run(
        runtime.process_lead(
            LeadProcessRequest(
                idempotency_key="idem_3",
                company_id="comp_345",
                metadata={"company_name": "Acme AI", "company_domain": "acme.ai"},
            )
        )
    )
    lead_id = processed.data["lead_id"]
    result = asyncio.run(
        runtime.advance_state(
            LeadAdvanceRequest(
                idempotency_key="idem_adv_1",
                lead_id=lead_id,
                from_state="brief_ready",
                to_state="booked",
                reason="invalid shortcut",
            )
        )
    )
    assert result.status == "failure"
    assert result.error is not None
    assert result.error.error_code == "INVALID_STATE_TRANSITION"
