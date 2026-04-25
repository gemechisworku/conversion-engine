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
from agent.services.email.schemas import InboundEmailEvent


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


def _runtime(*, email_service=None) -> OrchestrationRuntime:
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
        email_service=email_service,
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


def _set_awaiting_reply(runtime: OrchestrationRuntime, *, lead_id: str) -> None:
    session = runtime._state_repo.get_session_state(lead_id=lead_id) or {}
    runtime._state_repo.upsert_session_state(
        lead_id=lead_id,
        payload={**session, "current_stage": "awaiting_reply"},
    )


def test_handle_email_webhook_routes_reply_to_correct_lead() -> None:
    class _EmailServiceStub:
        async def handle_webhook(self, *, payload, headers, raw_body=None):
            del headers, raw_body
            data = payload["data"]
            return InboundEmailEvent(
                event_type="reply",
                provider_message_id=str(data["email_id"]),
                from_email=str(data["from"]),
                to_email=str(data["to"][0]),
                subject=str(data["subject"]),
                text_body=str(data["text"]),
                rfc_message_id=str(data["message_id"]),
                references=str(data["references"]),
                raw_payload_ref="abc123def4567890",
                raw_payload=payload,
            )

        async def get_received_email(self, *, email_id: str):
            assert email_id == "recv_555"
            return {
                "id": email_id,
                "from": "prospect@example.com",
                "to": [f"{lead_id}@chuairkoon.resend.app"],
                "subject": "Re: Intro",
                "text": "Can you share available times next week?",
                "html": "<p>Can you share available times next week?</p>",
                "message_id": "<inbound-555@example.com>",
                "headers": {"In-Reply-To": "<outbound@example.com>", "References": "<outbound@example.com>"},
                "received_at": "2026-04-24T21:44:51Z",
            }

    runtime = _runtime(email_service=_EmailServiceStub())
    processed = asyncio.run(
        runtime.process_lead(
            LeadProcessRequest(
                idempotency_key="idem_webhook_1",
                company_id="comp_webhook_1",
                metadata={"company_name": "Acme AI", "company_domain": "acme.ai"},
            )
        )
    )
    lead_id = processed.data["lead_id"]
    _set_awaiting_reply(runtime, lead_id=lead_id)

    payload = {
        "type": "email.received",
        "data": {
            "id": "re_555",
            "email_id": "recv_555",
            "message_id": "<inbound-555@example.com>",
            "from": "prospect@example.com",
            "to": [f"{lead_id}@chuairkoon.resend.app"],
            "subject": "Re: Intro",
            "text": "Can you share available times next week?",
            "references": "<outbound@example.com>",
        },
    }
    env = asyncio.run(runtime.handle_email_webhook(payload=payload, headers={}))
    assert env.status == "accepted"
    assert env.data["lead_id"] == lead_id
    assert env.data["state"] == "reply_received"
    assert env.data["next_action"] == "schedule"
    stored = runtime._state_repo.get_inbound_email(resend_email_id="recv_555")
    assert stored is not None
    assert stored["lead_id"] == lead_id
    assert stored["to_email"] == f"{lead_id}@chuairkoon.resend.app"


def test_handle_email_webhook_hydrates_content_from_received_email_api() -> None:
    class _EmailServiceStub:
        async def handle_webhook(self, *, payload, headers, raw_body=None):
            del headers, raw_body
            data = payload["data"]
            return InboundEmailEvent(
                event_type="reply",
                provider_message_id=str(data["email_id"]),
                from_email=str(data["from"]),
                to_email=str(data["to"][0]),
                subject=str(data["subject"]),
                text_body=None,
                rfc_message_id=str(data["message_id"]),
                references=str(data["references"]),
                raw_payload_ref="abc123def4567000",
                raw_payload=payload,
            )

        async def get_received_email(self, *, email_id: str):
            assert email_id == "recv_101"
            return {
                "id": "recv_101",
                "from": "prospect@example.com",
                "to": ["lead_hydrated_1@chuairkoon.resend.app"],
                "subject": "Re: Intro",
                "text": "Hydrated inbound email content",
                "message_id": "<inbound-hydrated@example.com>",
                "headers": {"In-Reply-To": "<outbound@example.com>"},
            }

    runtime = _runtime(email_service=_EmailServiceStub())
    lead_id = "lead_hydrated_1"
    runtime._state_repo.upsert_session_state(
        lead_id=lead_id,
        payload={
            "current_stage": "awaiting_reply",
            "next_best_action": "wait",
            "current_objective": "reply_wait",
            "brief_refs": [],
            "kb_refs": [],
            "pending_actions": [],
            "policy_flags": [],
            "handoff_required": False,
        },
    )
    payload = {
        "type": "email.received",
        "data": {
            "id": "re_recv_101",
            "email_id": "recv_101",
            "message_id": "<inbound-hydrated@example.com>",
            "from": "prospect@example.com",
            "to": [f"{lead_id}@chuairkoon.resend.app"],
            "subject": "Re: Intro",
            "references": "<outbound@example.com>",
        },
    }
    env = asyncio.run(runtime.handle_email_webhook(payload=payload, headers={}))
    assert env.status == "accepted"
    rows = runtime._state_repo.list_messages(lead_id=lead_id, limit=5)
    assert any("Hydrated inbound email content" in str(r.get("content")) for r in rows)


def test_handle_email_webhook_invalid_email_id_is_handled_gracefully() -> None:
    class _EmailServiceStub:
        async def handle_webhook(self, *, payload, headers, raw_body=None):
            del headers, raw_body
            return InboundEmailEvent(
                event_type="reply",
                provider_message_id=str(payload["data"]["email_id"]),
                raw_payload_ref="abc123def4567001",
                raw_payload=payload,
            )

        async def get_received_email(self, *, email_id: str):
            del email_id
            return None

    runtime = _runtime(email_service=_EmailServiceStub())
    payload = {"type": "email.received", "data": {"email_id": "recv_missing"}}
    env = asyncio.run(runtime.handle_email_webhook(payload=payload, headers={}))
    assert env.status == "accepted"
    assert env.data["processed"] is False
    assert env.data["reason"] == "received_email_fetch_failed"


def test_handle_email_webhook_ignores_non_received_events() -> None:
    class _EmailServiceStub:
        async def handle_webhook(self, *, payload, headers, raw_body=None):
            raise AssertionError("Should not parse non-email.received events")

        async def get_received_email(self, *, email_id: str):
            raise AssertionError("Should not fetch for non-email.received events")

    runtime = _runtime(email_service=_EmailServiceStub())
    env = asyncio.run(runtime.handle_email_webhook(payload={"type": "email.sent"}, headers={}))
    assert env.status == "accepted"
    assert env.data["ignored"] is True
    assert env.data["processed"] is False


def test_handle_email_webhook_rejects_malformed_to_address() -> None:
    class _EmailServiceStub:
        async def handle_webhook(self, *, payload, headers, raw_body=None):
            del headers, raw_body
            return InboundEmailEvent(
                event_type="reply",
                provider_message_id=str(payload["data"]["email_id"]),
                raw_payload_ref="abc123def4567002",
                raw_payload=payload,
            )

        async def get_received_email(self, *, email_id: str):
            del email_id
            return {"id": "recv_bad_to", "to": ["not-an-email"], "text": "Hello"}

    runtime = _runtime(email_service=_EmailServiceStub())
    payload = {"type": "email.received", "data": {"email_id": "recv_bad_to"}}
    env = asyncio.run(runtime.handle_email_webhook(payload=payload, headers={}))
    assert env.status == "accepted"
    assert env.data["processed"] is False
    assert env.data["reason"] == "invalid_to_address"


def test_handle_email_webhook_duplicate_is_idempotent_no_duplicate_db_row() -> None:
    lead_id = "lead_dupe_1"

    class _EmailServiceStub:
        async def handle_webhook(self, *, payload, headers, raw_body=None):
            del headers, raw_body
            return InboundEmailEvent(
                event_type="reply",
                provider_message_id=str(payload["data"]["email_id"]),
                raw_payload_ref="abc123def4567003",
                raw_payload=payload,
            )

        async def get_received_email(self, *, email_id: str):
            del email_id
            return {
                "id": "recv_dupe_1",
                "from": "prospect@example.com",
                "to": [f"{lead_id}@chuairkoon.resend.app"],
                "subject": "Re: Intro",
                "text": "Please send times.",
                "message_id": "<inbound-dupe@example.com>",
                "headers": {"In-Reply-To": "<outbound@example.com>"},
            }

    runtime = _runtime(email_service=_EmailServiceStub())
    runtime._state_repo.upsert_session_state(
        lead_id=lead_id,
        payload={
            "current_stage": "awaiting_reply",
            "next_best_action": "wait",
            "current_objective": "reply_wait",
            "brief_refs": [],
            "kb_refs": [],
            "pending_actions": [],
            "policy_flags": [],
            "handoff_required": False,
        },
    )
    payload = {"type": "email.received", "data": {"email_id": "recv_dupe_1"}}

    first = asyncio.run(runtime.handle_email_webhook(payload=payload, headers={}))
    second = asyncio.run(runtime.handle_email_webhook(payload=payload, headers={}))

    assert first.status == "accepted"
    assert second.status == "accepted"
    assert second.data["duplicate"] is True
    assert runtime._state_repo.count_inbound_emails(resend_email_id="recv_dupe_1") == 1


def test_handle_email_webhook_extracts_lead_id_from_recipient_local_part() -> None:
    lead_id = "lead_extract_1"

    class _EmailServiceStub:
        async def handle_webhook(self, *, payload, headers, raw_body=None):
            del headers, raw_body
            return InboundEmailEvent(
                event_type="reply",
                provider_message_id=str(payload["data"]["email_id"]),
                raw_payload_ref="abc123def4567004",
                raw_payload=payload,
            )

        async def get_received_email(self, *, email_id: str):
            del email_id
            return {
                "id": "recv_extract_1",
                "from": "prospect@example.com",
                "to": [f"{lead_id}@chuairkoon.resend.app"],
                "subject": "Re: Intro",
                "text": "Sounds good.",
                "message_id": "<inbound-extract@example.com>",
            }

    runtime = _runtime(email_service=_EmailServiceStub())
    runtime._state_repo.upsert_session_state(
        lead_id=lead_id,
        payload={
            "current_stage": "awaiting_reply",
            "next_best_action": "wait",
            "current_objective": "reply_wait",
            "brief_refs": [],
            "kb_refs": [],
            "pending_actions": [],
            "policy_flags": [],
            "handoff_required": False,
        },
    )
    payload = {"type": "email.received", "data": {"email_id": "recv_extract_1"}}
    env = asyncio.run(runtime.handle_email_webhook(payload=payload, headers={}))
    assert env.status == "accepted"
    assert env.data["lead_id"] == lead_id


def test_handle_email_webhook_falls_back_to_thread_headers_when_to_unmatched() -> None:
    lead_id = "lead_fallback_1"

    class _EmailServiceStub:
        async def handle_webhook(self, *, payload, headers, raw_body=None):
            del headers, raw_body
            return InboundEmailEvent(
                event_type="reply",
                provider_message_id=str(payload["data"]["email_id"]),
                raw_payload_ref="abc123def4567005",
                raw_payload=payload,
            )

        async def get_received_email(self, *, email_id: str):
            del email_id
            return {
                "id": "recv_fallback_1",
                "from": "prospect@example.com",
                "to": ["someone@other-domain.example"],
                "subject": "Re: Intro",
                "text": "Following up.",
                "message_id": "<inbound-fallback@example.com>",
                "headers": {"In-Reply-To": "<thread-anchor@example.com>"},
            }

    runtime = _runtime(email_service=_EmailServiceStub())
    runtime._state_repo.upsert_session_state(
        lead_id=lead_id,
        payload={
            "current_stage": "awaiting_reply",
            "next_best_action": "wait",
            "current_objective": "reply_wait",
            "brief_refs": [],
            "kb_refs": [],
            "pending_actions": [],
            "policy_flags": [],
            "handoff_required": False,
        },
    )
    runtime._state_repo.email_thread_record_inbound(
        lead_id=lead_id,
        inbound_rfc_message_id="<thread-anchor@example.com>",
        prior_references_fragment=None,
    )
    payload = {"type": "email.received", "data": {"email_id": "recv_fallback_1"}}
    env = asyncio.run(runtime.handle_email_webhook(payload=payload, headers={}))
    assert env.status == "accepted"
    assert env.data["lead_id"] == lead_id
