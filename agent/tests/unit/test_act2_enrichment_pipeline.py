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
from agent.services.enrichment.schemas import Firmographics


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
        url = str(request.url)
        if "consumerfinance.gov" in url:
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
        if "lite.duckduckgo.com" in url:
            return httpx.Response(200, text="<html></html>", headers={"Content-Type": "text/html"})
        if "wikipedia.org/w/api.php" in url:
            return httpx.Response(200, json={"query": {"search": []}})
        return httpx.Response(
            200,
            text=(
                "<html><head><title>FinCo announces platform update</title>"
                '<meta name="description" content="FinCo shared a public product and compliance update.">'
                "</head><body><p>FinCo announced a public platform update for buyers in financial services.</p>"
                "<time>2026-04-01</time></body></html>"
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


def test_news_retriever_uses_search_feed_and_ignores_crunchbase() -> None:
    settings = Settings()
    seen_urls: list[str] = []

    article = (
        "<html><head><title>FinCo announces new lending platform</title>"
        '<meta name="description" content="FinCo announced a public platform update.">'
        "</head><body><p>FinCo announced a public platform update for lending.</p></body></html>"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if "lite.duckduckgo.com" in str(request.url):
            link = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample-news.test%2Ffinco-platform"
            return httpx.Response(200, text=f'<html><a href="{link}">story</a></html>')
        if "wikipedia.org/w/api.php" in str(request.url):
            return httpx.Response(200, json={"query": {"search": []}})
        if "example-news.test" in str(request.url):
            return httpx.Response(200, text=article, headers={"Content-Type": "text/html"})
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    retriever = PublicNewsPlaywrightRetriever(settings=settings, http_client=http_client)
    brief = asyncio.run(
        retriever.build_news_brief(
            lead_id="lead_finco",
            enrichment_brief=asyncio.run(
                CrunchbaseAdapter(settings=settings).build_enrichment_brief(
                    lead_id="lead_finco",
                    company_name="FinCo",
                )
            ).model_copy(
                update={
                    "matched": True,
                    "firmographics": Firmographics(
                        company_name="FinCo",
                        website="https://finco.example",
                        crunchbase_url="https://www.crunchbase.com/organization/finco",
                    ),
                }
            ),
        )
    )
    asyncio.run(http_client.aclose())

    assert brief.found is True
    assert brief.url == "https://example-news.test/finco-platform"
    assert not any("crunchbase.com" in url for url in seen_urls)
    assert any("lite.duckduckgo.com" in url for url in seen_urls)


def test_news_retriever_rejects_blocked_pages() -> None:
    settings = Settings()

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><title>Attention Required! | Cloudflare</title><body>Sorry, you have been blocked</body></html>",
            headers={"Content-Type": "text/html"},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    retriever = PublicNewsPlaywrightRetriever(settings=settings, http_client=http_client)
    enrichment = asyncio.run(
        CrunchbaseAdapter(settings=settings).build_enrichment_brief(
            lead_id="lead_finco",
            company_name="FinCo",
        )
    ).model_copy(
        update={
            "matched": True,
            "firmographics": Firmographics(
                company_name="No Matching Company Name",
                website="https://finco.example",
            ),
        }
    )
    brief = asyncio.run(retriever.build_news_brief(lead_id="lead_finco", enrichment_brief=enrichment))
    asyncio.run(http_client.aclose())

    assert brief.found is False
    assert brief.error
    assert "empty_or_blocked" in brief.error or "blocked" in brief.error.lower()
