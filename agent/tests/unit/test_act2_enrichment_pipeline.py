from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.act2_pipeline import ActIIEnrichmentPipeline
from agent.services.enrichment.cfpb import CFPBComplaintAdapter
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.news_playwright import PublicNewsPlaywrightRetriever


def _write_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "id,name,website,contact_email,contact_phone,industries,num_employees,region,address,url",
                (
                    'finco,FinCo,https://finco.example,buyer@finco.example,+15551234567,'
                    '"[{""id"":""fintech"",""value"":""Financial Services""}]",51-100,NA,New York,'
                    "https://www.crunchbase.com/organization/finco"
                ),
            ]
        ),
        encoding="utf-8",
    )


def _workspace_tmp() -> Path:
    path = Path("outputs/test_act2") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_act2_pipeline_writes_three_required_briefs() -> None:
    tmp_path = _workspace_tmp()
    csv_path = tmp_path / "crunchbase.csv"
    out_dir = tmp_path / "evidence"
    _write_csv(csv_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        if "consumerfinance.gov" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "hits": {
                        "hits": [
                            {"_source": {"issue": "Incorrect information on your report", "product": "Credit reporting"}},
                            {"_source": {"issue": "Incorrect information on your report", "product": "Credit reporting"}},
                            {"_source": {"issue": "Managing an account", "product": "Checking account"}},
                            {"_source": {"issue": "Trouble during payment process", "product": "Money transfer"}},
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            text=(
                "<html><head><title>FinCo announces platform update</title>"
                '<meta name="description" content="FinCo shared a public product and compliance update.">'
                "</head><body><time>2026-04-01</time></body></html>"
            ),
            headers={"Content-Type": "text/html"},
        )

    settings = Settings(
        challenge_mode=False,
        sink_routing_enabled=True,
        crunchbase_dataset_path=str(csv_path),
        act2_evidence_dir=str(out_dir),
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    crunchbase = CrunchbaseAdapter(settings=settings)
    pipeline = ActIIEnrichmentPipeline(
        settings=settings,
        crunchbase=crunchbase,
        cfpb=CFPBComplaintAdapter(settings=settings, http_client=http_client),
        news=PublicNewsPlaywrightRetriever(settings=settings, http_client=http_client),
    )

    context = asyncio.run(
        pipeline.run_before_reply(
            lead_id="lead_finco",
            company_id=None,
            from_email="buyer@finco.example",
            from_number="+15551234567",
        )
    )
    asyncio.run(http_client.aclose())

    assert context.enrichment_brief.matched is True
    assert context.enrichment_brief.match_type == "email_domain"
    assert context.compliance_brief.applicable is True
    assert context.compliance_brief.complaint_count == 4
    assert [issue.issue for issue in context.compliance_brief.top_issues][:2] == [
        "Incorrect information on your report",
        "Managing an account",
    ]
    assert context.news_brief.found is True
    for artifact_name in ("enrichment_brief", "compliance_brief", "news_brief"):
        assert Path(context.artifact_paths[artifact_name]).exists()


def test_act2_pipeline_skips_cfpb_for_non_financial_company() -> None:
    tmp_path = _workspace_tmp()
    csv_path = tmp_path / "crunchbase.csv"
    csv_path.write_text(
        "id,name,website,contact_email,industries\n"
        'retailco,RetailCo,https://retail.example,buyer@retail.example,"[{""id"":""retail"",""value"":""Retail""}]"\n',
        encoding="utf-8",
    )
    settings = Settings(
        challenge_mode=False,
        sink_routing_enabled=True,
        crunchbase_dataset_path=str(csv_path),
        act2_evidence_dir=str(tmp_path / "evidence"),
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(404)))
    crunchbase = CrunchbaseAdapter(settings=settings)
    pipeline = ActIIEnrichmentPipeline(
        settings=settings,
        crunchbase=crunchbase,
        cfpb=CFPBComplaintAdapter(settings=settings, http_client=http_client),
        news=PublicNewsPlaywrightRetriever(settings=settings, http_client=http_client),
    )

    context = asyncio.run(
        pipeline.run_before_reply(
            lead_id="lead_retail",
            company_id=None,
            from_email="buyer@retail.example",
        )
    )
    asyncio.run(http_client.aclose())

    assert context.enrichment_brief.matched is True
    assert context.compliance_brief.applicable is False
    assert context.compliance_brief.skipped_reason == "not_financial_services"
