"""Orchestration API readiness: health, optional API key, CORS."""

from __future__ import annotations

from agent.api.orchestration_app import create_orchestration_app
from agent.config.settings import get_settings
from fastapi.testclient import TestClient


def test_health_requires_no_api_key() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_openapi_json_requires_no_api_key() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/openapi.json")
    assert res.status_code == 200
    assert "openapi" in res.json()


def test_api_key_enforced_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATION_API_KEY", "unit-test-orchestration-secret")
    get_settings.cache_clear()
    try:
        app = create_orchestration_app()
        with TestClient(app) as client:
            res = client.get("/lead/any_lead/state")
        assert res.status_code == 401
        body = res.json()
        assert body["status"] == "failure"
        assert body["error"]["error_code"] == "UNAUTHORIZED"

        with TestClient(app) as client:
            ok = client.get(
                "/lead/any_lead/state",
                headers={"X-API-Key": "unit-test-orchestration-secret"},
            )
        assert ok.status_code == 200
        assert ok.json()["status"] == "failure"
        assert ok.json()["error"]["error_code"] == "INVALID_INPUT"

        with TestClient(app) as client:
            bearer = client.get(
                "/lead/any_lead/state",
                headers={"Authorization": "Bearer unit-test-orchestration-secret"},
            )
        assert bearer.status_code == 200
    finally:
        monkeypatch.delenv("ORCHESTRATION_API_KEY", raising=False)
        get_settings.cache_clear()


def test_cors_preflight_when_origins_configured(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATION_CORS_ORIGINS", "http://localhost:3000")
    get_settings.cache_clear()
    try:
        app = create_orchestration_app()
        with TestClient(app) as client:
            res = client.options(
                "/lead/process",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-api-key",
                },
            )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    finally:
        monkeypatch.delenv("ORCHESTRATION_CORS_ORIGINS", raising=False)
        get_settings.cache_clear()
