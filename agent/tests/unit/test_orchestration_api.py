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


def test_get_pipeline_unknown_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/pipelines/lead_does_not_exist_zzzz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"


def test_get_lead_briefs_unknown_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/lead/lead_does_not_exist_zzzz/briefs")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"


def test_get_lead_messages_unknown_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/lead/lead_does_not_exist_zzzz/messages")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"


def test_get_lead_conversation_unknown_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/lead/lead_does_not_exist_zzzz/conversation")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"


def test_get_handoffs_returns_success_envelope() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.get("/handoffs?limit=20")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert isinstance(body["data"].get("handoffs"), list)


def test_resend_webhook_route_is_registered() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.post("/webhooks/resend", json={"type": "unknown"})
    assert res.status_code == 200


def test_post_lead_respond_unknown_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.post(
            "/lead/respond",
            json={
                "idempotency_key": "idem_test_respond_unknown",
                "lead_id": "lead_does_not_exist_zzzz",
                "channel": "email",
                "content": "Hello there",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"


def test_post_lead_schedule_prepare_unknown_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.post(
            "/lead/schedule/prepare",
            json={"lead_id": "lead_does_not_exist_zzzz"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"


def test_post_lead_schedule_book_unknown_returns_failure() -> None:
    app = create_orchestration_app()
    with TestClient(app) as client:
        res = client.post(
            "/lead/schedule/book",
            json={
                "idempotency_key": "idem_test_schedule_book_unknown",
                "lead_id": "lead_does_not_exist_zzzz",
                "confirmed_by_prospect": True,
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failure"
    assert body["error"]["error_code"] == "INVALID_INPUT"
