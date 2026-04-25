"""Orchestration API auth and CORS helpers for browser / SPA clients."""

from __future__ import annotations

import re
from typing import Iterable

from starlette.requests import Request


def parse_cors_origins(raw: str) -> list[str]:
    """Comma-separated origins; empty string → no CORS middleware (same-origin only)."""
    if not raw.strip():
        return []
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def extract_client_api_key(request: Request) -> str | None:
    """Read `X-API-Key` or `Authorization: Bearer <token>`."""
    key = (request.headers.get("x-api-key") or "").strip()
    if key:
        return key
    auth = (request.headers.get("authorization") or "").strip()
    m = re.match(r"Bearer\s+(.+)$", auth, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def public_paths() -> frozenset[str]:
    return frozenset(
        {
            "/health",
            "/openapi.json",
            "/docs",
            "/redoc",
            "/webhooks/resend",
        }
    )


def is_browser_preflight(request: Request) -> bool:
    return request.method == "OPTIONS"
