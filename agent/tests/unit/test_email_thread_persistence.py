from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from agent.config.settings import Settings
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.email.threading import persist_inbound_resend_webhook
from agent.services.email.webhook import ResendWebhookParser


def test_email_thread_roundtrip_from_webhook() -> None:
    db_path = Path(f"outputs/test_email_thread_{uuid4().hex}.db")
    settings = Settings(
        state_db_path=str(db_path),
        resend_webhook_secret="",
        challenge_mode=False,
        sink_routing_enabled=True,
    )
    repo = SQLiteStateRepository(db_path=settings.state_db_path)
    repo.ensure_email_thread(lead_id="lead_fixture_1")

    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "fixtures" / "webhooks" / "resend" / "reply_event.json").read_text(
            encoding="utf-8"
        )
    )
    parser = ResendWebhookParser(settings)
    event = parser.parse(payload=payload, headers={})
    asyncio.run(persist_inbound_resend_webhook(state_repo=repo, event=event))

    last_in, refs = repo.get_email_thread_reply_headers(lead_id="lead_fixture_1")
    assert last_in == "<prospect-reply-abc@mail.example>"
    assert "<first@id.com>" in (refs or "")
    assert "<outbound-ses-id@amazonses.com>" in (refs or "")


def test_email_thread_roundtrip_resolves_lead_id_from_reply_to_recipient() -> None:
    db_path = Path(f"outputs/test_email_thread_route_{uuid4().hex}.db")
    settings = Settings(
        state_db_path=str(db_path),
        resend_webhook_secret="",
        challenge_mode=False,
        sink_routing_enabled=True,
        resend_reply_domain="chuairkoon.resend.app",
    )
    repo = SQLiteStateRepository(db_path=settings.state_db_path)
    repo.ensure_email_thread(lead_id="lead_routed_1")

    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "webhooks"
            / "resend"
            / "reply_event_reply_to_routed.json"
        ).read_text(encoding="utf-8")
    )
    parser = ResendWebhookParser(settings)
    event = parser.parse(payload=payload, headers={})
    lead_id = asyncio.run(
        persist_inbound_resend_webhook(
            state_repo=repo,
            event=event,
            reply_domain=settings.resend_reply_domain,
        )
    )

    assert lead_id == "lead_routed_1"
    last_in, refs = repo.get_email_thread_reply_headers(lead_id="lead_routed_1")
    assert last_in == "<prospect-reply-routed@mail.example>"
    assert "<outbound-ses-routed@amazonses.com>" in (refs or "")
