from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from agent.config.settings import Settings, get_settings
from agent.graphs.lead_graph import run_lead_intake
from agent.graphs.state import LeadGraphState
from agent.services.enrichment.llm import OpenRouterJSONClient


def test_openrouter_connectivity_uses_models_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/models"
        return httpx.Response(200, json={"data": []})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        openrouter_api_key="test_key",
        openrouter_api_url="https://openrouter.ai/api/v1/chat/completions",
        openrouter_trust_env_proxy=False,
    )
    client = OpenRouterJSONClient(settings=settings, http_client=http_client)
    ok, reason = asyncio.run(client.check_connectivity(trace_id="t1", lead_id="l1"))
    asyncio.run(http_client.aclose())

    assert ok is True
    assert reason is None


def test_run_lead_intake_fails_when_llm_is_required_and_unavailable() -> None:
    class _FailingLLM:
        configured = True

        async def check_connectivity(self, *, trace_id: str | None = None, lead_id: str | None = None):
            _ = (trace_id, lead_id)
            return False, "proxy_connection_refused"

    settings = Settings(
        enrichment_require_llm=True,
        enrichment_check_llm_connectivity=True,
        openrouter_api_key="test_key",
    )
    state = LeadGraphState(
        lead_id="lead_llm_required",
        company_id="company_llm_required",
        current_stage="enriching",
    )
    with pytest.raises(RuntimeError, match="LLM connectivity required but unavailable"):
        asyncio.run(
            run_lead_intake(
                state=state,
                company_name="Acme",
                company_domain="acme.ai",
                services={
                    "settings": settings,
                    "llm": _FailingLLM(),
                    "trace_id": "trace_llm_required",
                },
            )
        )


def test_get_settings_clears_proxy_env_when_http_trust_env_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_TRUST_ENV_PROXY", "false")
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.http_trust_env_proxy is False
    assert "HTTP_PROXY" not in os.environ
    assert "HTTPS_PROXY" not in os.environ
    assert "ALL_PROXY" not in os.environ
