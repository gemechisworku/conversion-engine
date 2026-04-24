from __future__ import annotations

from agent.services.email.rfc_ids import merge_references_header, normalize_message_id


def test_normalize_message_id_adds_brackets() -> None:
    assert normalize_message_id("abc@x") == "<abc@x>"


def test_merge_references_header_dedupes() -> None:
    m = merge_references_header("<a@b>", "<a@b> <c@d>", "<c@d>")
    assert m.split() == ["<a@b>", "<c@d>"]
