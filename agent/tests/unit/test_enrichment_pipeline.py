from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.jobs_playwright import JobsPlaywrightCollector
from agent.services.enrichment.layoffs import LayoffsAdapter
from agent.services.enrichment.leadership import LeadershipChangeDetector
from agent.services.enrichment.merger import EnrichmentPipeline


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "enrichment"


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "crunchbase_dataset_path": str(FIXTURE_DIR / "crunchbase_sample.json"),
        "layoffs_csv_path": str(FIXTURE_DIR / "layoffs_sample.csv"),
        "leadership_feed_url": str(FIXTURE_DIR / "leadership_sample.json"),
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_crunchbase_adapter_returns_normalized_output() -> None:
    adapter = CrunchbaseAdapter(settings=_settings())
    snapshot = asyncio.run(adapter.collect(company_id="comp_123", company_domain="acme.ai"))
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert snapshot.confidence >= 0.8
    assert summary["company_name"] == "Acme AI"
    assert summary["funding_round"] == "Series A"


def test_jobs_adapter_returns_role_counts() -> None:
    html = """
    <html>
      <body>
        <div>Senior Software Engineer</div>
        <div>ML Platform Engineer</div>
        <div>Data Engineer</div>
      </body>
    </html>
    """

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"Content-Type": "text/html"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collector = JobsPlaywrightCollector(settings=_settings(), http_client=http_client)
    snapshot = asyncio.run(collector.collect(company_domain="acme.ai"))
    asyncio.run(http_client.aclose())
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert summary["engineering_role_count"] >= 2
    assert summary["ai_adjacent_role_count"] >= 1
    assert "Senior Software Engineer" in summary["role_titles"]
    assert "ML Platform Engineer" in summary["role_titles"]


def test_layoffs_adapter_parses_csv_match() -> None:
    adapter = LayoffsAdapter(settings=_settings())
    snapshot = asyncio.run(adapter.collect(company_name="Acme AI"))
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert summary["matched"] is True
    assert summary["affected_count"] == 45


def test_layoffs_adapter_uses_reference_date_window() -> None:
    path = Path("outputs/test-fixtures/layoffs_reference.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "company,date,laid_off,%\nAcme AI,2025-01-15,10,5\n",
        encoding="utf-8",
    )
    adapter = LayoffsAdapter(
        settings=_settings(
            layoffs_csv_path=str(path),
            enrichment_reference_date="2025-02-15T00:00:00Z",
        )
    )
    snapshot = asyncio.run(adapter.collect(company_name="Acme AI"))
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert summary["matched"] is True


def test_leadership_adapter_detects_change() -> None:
    adapter = LeadershipChangeDetector(settings=_settings())
    snapshot = asyncio.run(adapter.collect(company_name="Acme AI"))
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert summary["matched"] is True
    assert summary["role_name"] == "CTO"


def test_leadership_adapter_uses_reference_date_window() -> None:
    path = Path("outputs/test-fixtures/leadership_reference.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
        [
          {
            "company": "Acme AI",
            "role_name": "CTO",
            "person": "Taylor",
            "change_type": "hire",
            "change_date": "2025-02-01",
            "source_url": "https://example.com/news"
          }
        ]
        """.strip(),
        encoding="utf-8",
    )
    adapter = LeadershipChangeDetector(
        settings=_settings(
            leadership_feed_url=str(path),
            enrichment_reference_date="2025-02-20T00:00:00Z",
        )
    )
    snapshot = asyncio.run(adapter.collect(company_name="Acme AI"))
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert summary["matched"] is True
    assert summary["role_name"] == "CTO"


def test_merger_produces_complete_schema_and_partial_confidence() -> None:
    crunchbase = asyncio.run(CrunchbaseAdapter(settings=_settings()).collect(company_id="comp_123"))
    jobs = asyncio.run(JobsPlaywrightCollector(settings=_settings()).collect(company_domain="missing-domain.example"))
    layoffs = asyncio.run(LayoffsAdapter(settings=_settings()).collect(company_name="Acme AI"))
    merger = EnrichmentPipeline()
    artifact = merger.merge(
        company_id="comp_123",
        crunchbase=crunchbase,
        job_posts=jobs,
        layoffs=layoffs,
        leadership_changes=None,
    )

    assert set(artifact.signals.keys()) == {
        "crunchbase",
        "job_posts",
        "layoffs",
        "leadership_changes",
        "tech_stack",
    }
    assert artifact.merged_confidence["leadership_signal"] <= 0.2


def test_jobs_adapter_respects_robots_block() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /careers\n")
        return httpx.Response(200, text="<div>ML Engineer</div>", headers={"Content-Type": "text/html"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collector = JobsPlaywrightCollector(settings=_settings(), http_client=http_client)
    snapshot = asyncio.run(collector.collect(company_domain="acme.ai", company_name="Acme AI"))
    asyncio.run(http_client.aclose())
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert "https://acme.ai/careers" in summary["robots_blocked_urls"]


def test_crunchbase_collect_includes_recent_funding_events() -> None:
    path = Path("outputs/test-fixtures/recent_funding.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
        [{
          "id": "funded_co",
          "name": "Funded Co",
          "website": "https://funded.example",
          "industries": "[{\\"id\\":\\"fintech\\",\\"value\\":\\"FinTech\\"}]",
          "funding_rounds_list": "[{\\"investment_type\\":\\"Series A\\",\\"announced_on\\":\\"2026-03-01\\",\\"money_raised\\":{\\"value_usd\\":5000000}}]",
          "builtwith_tech": "[{\\"name\\":\\"OpenAI\\"}]"
        }]
        """.strip(),
        encoding="utf-8",
    )
    snapshot = asyncio.run(
        CrunchbaseAdapter(settings=_settings(crunchbase_dataset_path=str(path))).collect(
            company_id="funded_co",
            company_domain="funded.example",
        )
    )
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert summary["funding_events_180d"][0]["round"] == "Series A"
    assert "OpenAI" in summary["tech_stack"]


def test_jobs_module_has_no_interactive_auth_flow() -> None:
    file_path = Path(__file__).resolve().parents[2] / "services" / "enrichment" / "jobs_playwright.py"
    content = file_path.read_text(encoding="utf-8").lower()
    blocked_patterns = ["page.fill(", "input[type=password]", "solve_", "anti-bot", "stealth"]
    for pattern in blocked_patterns:
        assert pattern not in content


def test_jobs_adapter_ignores_keyword_noise_without_role_suffix() -> None:
    html = """
    <html>
      <body>
        <div>ai ml data platform</div>
        <div>machine learning stack</div>
      </body>
    </html>
    """

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"Content-Type": "text/html"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collector = JobsPlaywrightCollector(settings=_settings(), http_client=http_client)
    snapshot = asyncio.run(collector.collect(company_domain="acme.ai"))
    asyncio.run(http_client.aclose())
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert summary["engineering_role_count"] == 0
    assert summary["ai_adjacent_role_count"] == 0


def test_reference_date_keeps_historical_funding_window_active() -> None:
    path = Path("outputs/test-fixtures/reference_funding.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
        [{
          "id": "hist_co",
          "name": "Historical Co",
          "website": "https://hist.example",
          "funding_rounds_list": "[{\\"investment_type\\":\\"Series B\\",\\"announced_on\\":\\"2025-01-15\\",\\"money_raised\\":{\\"value_usd\\":9000000}}]"
        }]
        """.strip(),
        encoding="utf-8",
    )
    snapshot = asyncio.run(
        CrunchbaseAdapter(
            settings=_settings(
                crunchbase_dataset_path=str(path),
                enrichment_reference_date="2025-03-01T00:00:00Z",
            )
        ).collect(company_id="hist_co", company_domain="hist.example")
    )
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert len(summary["funding_events_180d"]) == 1
    assert summary["funding_events_180d"][0]["round"] == "Series B"


def test_crunchbase_collect_normalizes_csv_specific_core_fields() -> None:
    path = Path("outputs/test-fixtures/crunchbase_csv_like.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
        [{
          "id": "csv_like_co",
          "name": "CSV Like Co",
          "url": "https://www.crunchbase.com/organization/csv-like-co",
          "website": "https://csvlike.example",
          "address": "Chicago, Illinois, United States, North America",
          "region": "NA",
          "country_code": "US",
          "company_type": "for_profit",
          "legal_name": "CSV Like Co, Inc.",
          "about": "Builds industrial automation software.",
          "founded_date": "2020-01-01",
          "operating_status": "active",
          "investment_stage": "Seed",
          "funds_total": "{\\"currency\\":\\"USD\\",\\"value_usd\\":7000000}",
          "funding_rounds_list": "[{\\"funding_round\\":{\\"value\\":\\"Series A\\"},\\"announced_on\\":\\"2026-03-10\\",\\"money_raised\\":{\\"value_usd\\":5000000}}]"
        }]
        """.strip(),
        encoding="utf-8",
    )
    snapshot = asyncio.run(
        CrunchbaseAdapter(settings=_settings(crunchbase_dataset_path=str(path))).collect(
            company_id="csv_like_co",
            company_domain="csvlike.example",
        )
    )
    summary = snapshot.summary if isinstance(snapshot.summary, dict) else {}

    assert summary["crunchbase_url"] == "https://www.crunchbase.com/organization/csv-like-co"
    assert summary["location"] == "Chicago, Illinois, United States, North America"
    assert summary["region"] == "NA"
    assert summary["country_code"] == "US"
    assert summary["company_type"] == "for_profit"
    assert summary["legal_name"] == "CSV Like Co, Inc."
    assert summary["description"] == "Builds industrial automation software."
    assert summary["founded_date"] == "2020-01-01"
    assert summary["operating_status"] == "active"
    assert summary["funding_round"] == "Series A"
    assert summary["funding_amount_usd"] == 5000000
    assert summary["funding_total_usd"] == 7000000
