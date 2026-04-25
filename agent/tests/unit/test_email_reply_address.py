from __future__ import annotations

from agent.services.email.reply_address import (
    build_lead_reply_address,
    build_lead_reply_local_part,
    extract_lead_id_from_reply_address,
)


def test_build_lead_reply_address_uses_safe_lead_id() -> None:
    reply_to = build_lead_reply_address(lead_id="lead_123", domain="chuairkoon.resend.app")
    assert reply_to == "lead_123@chuairkoon.resend.app"


def test_build_lead_reply_address_encodes_unsafe_lead_id() -> None:
    local_part = build_lead_reply_local_part("lead id/unsafe")
    assert local_part.startswith("lid__")
    extracted = extract_lead_id_from_reply_address(
        f"{local_part}@chuairkoon.resend.app",
        domain="chuairkoon.resend.app",
    )
    assert extracted == "lead id/unsafe"
