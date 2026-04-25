from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from agent.config.settings import Settings
import json

import httpx

from agent.services.enrichment.ai_maturity import score_ai_maturity, score_ai_maturity_with_llm
from agent.services.enrichment.competitor_gap import CompetitorGapAnalyst
from agent.services.enrichment.icp_classifier import classify_icp
from agent.services.enrichment.llm import OpenRouterJSONClient
import agent.services.enrichment.competitor_gap as competitor_gap_module
from agent.services.enrichment.schemas import EnrichmentArtifact, SignalSnapshot


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "enrichment"


def _artifact() -> EnrichmentArtifact:
    return EnrichmentArtifact(
        company_id="comp_123",
        generated_at=datetime.now(UTC),
        signals={
            "crunchbase": SignalSnapshot(
                summary={
                    "company_id": "comp_123",
                    "company_name": "Acme AI",
                    "industry": "ai",
                    "funding_round": "Series A",
                    "funding_date": "2026-02-15T00:00:00Z",
                },
                confidence=0.9,
            ),
            "job_posts": SignalSnapshot(
                summary={
                    "engineering_role_count": 9,
                    "ai_adjacent_role_count": 4,
                    "role_titles": ["ML Engineer", "Data Engineer", "Backend Engineer"],
                },
                confidence=0.85,
            ),
            "layoffs": SignalSnapshot(
                summary={"matched": False, "affected_percent": 0},
                confidence=0.7,
            ),
            "leadership_changes": SignalSnapshot(
                summary={"matched": True, "role_name": "CTO", "date": "2026-03-01T00:00:00Z"},
                confidence=0.8,
            ),
        },
        merged_confidence={},
    )


def _settings() -> Settings:
    return Settings(crunchbase_dataset_path=str(FIXTURE_DIR / "crunchbase_sample.json"))


def _settings_with_openrouter() -> Settings:
    return Settings(
        crunchbase_dataset_path=str(FIXTURE_DIR / "crunchbase_sample.json"),
        openrouter_api_key="test_key",
        openrouter_api_url="https://openrouter.test/chat/completions",
    )


def test_ai_maturity_scoring_output() -> None:
    artifact = _artifact()
    score = score_ai_maturity(company_id="comp_123", artifact=artifact)
    assert 0 <= score.score <= 3
    assert score.score >= 2
    assert score.confidence >= 0.6
    assert score.signals


def test_ai_maturity_scoring_can_use_openrouter_json() -> None:
    artifact = _artifact()
    deterministic = score_ai_maturity(company_id="comp_123", artifact=artifact)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    **deterministic.model_dump(mode="json"),
                                    "score": 3,
                                    "confidence": 0.81,
                                }
                            )
                        }
                    }
                ]
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    llm = OpenRouterJSONClient(settings=_settings_with_openrouter(), http_client=http_client)
    score = asyncio.run(score_ai_maturity_with_llm(company_id="comp_123", artifact=artifact, llm=llm))
    asyncio.run(http_client.aclose())

    assert score.score == 3
    assert score.confidence == 0.81


def test_openrouter_generate_model_writes_per_call_log_success(tmp_path: Path) -> None:
    artifact = _artifact()
    deterministic = score_ai_maturity(company_id="comp_123", artifact=artifact)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(deterministic.model_dump(mode="json"))}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    settings = Settings(
        crunchbase_dataset_path=str(FIXTURE_DIR / "crunchbase_sample.json"),
        openrouter_api_key="test_key",
        openrouter_api_url="https://openrouter.test/chat/completions",
        llm_call_log_dir=str(tmp_path / "llm_calls"),
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    llm = OpenRouterJSONClient(settings=settings, http_client=http_client)
    score = asyncio.run(score_ai_maturity_with_llm(company_id="comp_123", artifact=artifact, llm=llm))
    asyncio.run(http_client.aclose())

    files = list((tmp_path / "llm_calls").glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["model"] == settings.openrouter_model
    assert payload["parsed_output"]["company_id"] == "comp_123"
    assert payload["token_usage"]["prompt_tokens"] == 11
    assert payload["token_usage"]["completion_tokens"] == 7
    assert payload["token_usage"]["total_tokens"] == 18
    assert score.company_id == "comp_123"


def test_openrouter_generate_model_writes_per_call_log_error(tmp_path: Path) -> None:
    artifact = _artifact()

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    settings = Settings(
        crunchbase_dataset_path=str(FIXTURE_DIR / "crunchbase_sample.json"),
        openrouter_api_key="test_key",
        openrouter_api_url="https://openrouter.test/chat/completions",
        llm_call_log_dir=str(tmp_path / "llm_calls"),
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    llm = OpenRouterJSONClient(settings=settings, http_client=http_client)
    score = asyncio.run(score_ai_maturity_with_llm(company_id="comp_123", artifact=artifact, llm=llm))
    asyncio.run(http_client.aclose())

    files = list((tmp_path / "llm_calls").glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["response_status_code"] == 429
    assert "HTTPStatusError" in (payload["error"] or "")
    assert payload["token_usage"]["total_tokens"] == 0
    assert score.company_id == "comp_123"


def test_icp_classifier_output() -> None:
    artifact = _artifact()
    score = score_ai_maturity(company_id="comp_123", artifact=artifact)
    classification = classify_icp(artifact=artifact, ai_maturity=score)
    assert classification.primary_segment in {
        "segment_1_series_a_b",
        "segment_2_mid_market_restructure",
        "segment_3_leadership_transition",
        "segment_4_specialized_capability",
        "abstain",
    }
    assert 0 <= classification.confidence <= 1


def test_competitor_gap_brief_generation() -> None:
    artifact = _artifact()
    score = score_ai_maturity(company_id="comp_123", artifact=artifact)
    peer_path = Path("outputs/test-fixtures/competitor_peers.json")
    peer_path.parent.mkdir(parents=True, exist_ok=True)
    peer_path.write_text(
        json.dumps(
            [
                {"id": "comp_123", "name": "Acme AI", "industries": [{"value": "ai"}]},
                *[
                    {
                        "id": f"peer_{idx}",
                        "name": f"Peer {idx}",
                        "industries": [{"value": "ai"}],
                        "builtwith_tech": [{"name": "OpenAI"}],
                        "ai_roles": idx % 3,
                    }
                    for idx in range(1, 7)
                ],
            ]
        ),
        encoding="utf-8",
    )
    analyst = CompetitorGapAnalyst(settings=Settings(crunchbase_dataset_path=str(peer_path)))
    gap = asyncio.run(
        analyst.build_brief(
            lead_id="lead_123",
            company_id="comp_123",
            artifact=artifact,
            ai_maturity=score,
        )
    )
    assert gap.gap_brief_id
    assert 0 <= gap.sector_percentile <= 1
    assert gap.confidence > 0
    assert 5 <= len(gap.comparison_set) <= 10


def test_competitor_gap_uses_default_crunchbase_dataset(monkeypatch) -> None:
    peer_path = Path("outputs/test-fixtures/default_competitor_peers.json")
    peer_path.parent.mkdir(parents=True, exist_ok=True)
    peer_path.write_text(
        json.dumps(
            [
                {"id": "comp_123", "name": "Acme AI", "industries": [{"value": "SaaS"}], "num_employees": "51-100"},
                *[
                    {
                        "id": f"default_peer_{idx}",
                        "name": f"Default Peer {idx}",
                        "industries": [{"value": "SaaS"}],
                        "num_employees": "51-100",
                        "builtwith_tech": [{"name": "Databricks"}],
                    }
                    for idx in range(1, 6)
                ],
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(competitor_gap_module, "DEFAULT_CRUNCHBASE_DATASET_PATH", str(peer_path))
    artifact = _artifact()
    score = score_ai_maturity(company_id="comp_123", artifact=artifact)
    analyst = CompetitorGapAnalyst(settings=Settings(crunchbase_dataset_path=""))
    gap = asyncio.run(
        analyst.build_brief(
            lead_id="lead_123",
            company_id="comp_123",
            artifact=artifact,
            ai_maturity=score,
        )
    )

    assert len(gap.comparison_set) >= 5
    assert all(record.company_name.startswith("Default Peer") for record in gap.comparison_set)
