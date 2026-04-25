from __future__ import annotations

from fastapi.testclient import TestClient

from agent.api.orchestration_app import create_orchestration_app


def test_get_lead_state_unknown_returns_failure_envelope() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/lead/lead_does_not_exist_zzzz/state")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"


def test_get_memory_evidence_unknown_lead_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/memory/evidence/lead_does_not_exist_zzzz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"


def test_get_pipelines_returns_success_envelope() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/pipelines?limit=20")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert isinstance(body["data"].get("pipelines"), list)


def test_delete_pipeline_unknown_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.delete("/pipelines/lead_does_not_exist_zzzz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"
