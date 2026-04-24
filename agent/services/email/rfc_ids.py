"""Normalize and merge RFC 5322 Message-Id / References values."""

from __future__ import annotations

import re


def normalize_message_id(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    if text.startswith("<") and text.endswith(">"):
        return text
    return f"<{text}>"


def merge_references_header(*parts: str | None) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        if not part or not str(part).strip():
            continue
        for token in re.split(r"\s+", str(part).strip()):
            mid = normalize_message_id(token.strip()) if token.strip() else None
            if mid and mid not in seen:
                seen.add(mid)
                ordered.append(mid)
    return " ".join(ordered)
