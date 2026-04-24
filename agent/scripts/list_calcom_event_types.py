"""List available Cal.com event types for the configured API key."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
import re
import sys
from pathlib import Path

import httpx

# Allow running directly via `python agent/scripts/list_calcom_event_types.py`
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.config.settings import get_settings


def _safe_json(response: httpx.Response) -> dict:
    try:
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else {"payload": parsed}
    except ValueError:
        return {}


def _extract_slugs(profile_html: str, username: str) -> list[str]:
    pattern = rf"/{re.escape(username)}/([a-zA-Z0-9][a-zA-Z0-9\-_]*)"
    candidates = re.findall(pattern, profile_html)
    unique: list[str] = []
    seen: set[str] = set()
    for slug in candidates:
        normalized = slug.strip().lower()
        if not normalized or normalized in {"book"}:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(slug.strip())
    return unique


async def _validate_slug_event_types(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    username: str,
    slugs: list[str],
) -> list[dict]:
    start = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    end = (datetime.now(UTC) + timedelta(days=7)).date().isoformat()
    valid: list[dict] = []
    for slug in slugs:
        response = await client.get(
            f"{base_url}/slots",
            headers=headers,
            params={
                "eventTypeSlug": slug,
                "username": username,
                "start": start,
                "end": end,
                "timeZone": "UTC",
                "format": "range",
            },
        )
        payload = _safe_json(response)
        if response.status_code != 200:
            continue
        data = payload.get("data", {})
        slot_count = (
            sum(len(day_slots) for day_slots in data.values() if isinstance(day_slots, list))
            if isinstance(data, dict)
            else 0
        )
        valid.append(
            {
                "id": None,
                "title": None,
                "slug": slug,
                "lengthInMinutes": None,
                "slot_count_next_7_days": slot_count,
            }
        )
    return valid


async def main() -> None:
    # Implements: FR-11, FR-15
    # Workflow: scheduling_and_booking.md
    # Schema: booking_event.md
    # API: scheduling_api.md
    settings = get_settings()
    settings.require("calcom_api_key")

    base_url = settings.calcom_api_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.calcom_api_key}",
        "Accept": "application/json",
        "cal-api-version": "2024-09-04",
    }

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        response = await client.get(f"{base_url}/event-types", headers=headers)
        payload = _safe_json(response)

        if response.status_code == 200:
            data = payload.get("data", [])
            rows = data if isinstance(data, list) else []
            minimal = []
            for event_type in rows:
                if not isinstance(event_type, dict):
                    continue
                minimal.append(
                    {
                        "id": event_type.get("id"),
                        "title": event_type.get("title"),
                        "slug": event_type.get("slug"),
                        "lengthInMinutes": event_type.get("lengthInMinutes"),
                    }
                )
            result = {
                "ok": True,
                "source": "event_types_endpoint",
                "count": len(minimal),
                "event_types": minimal,
            }
            print(json.dumps(result, indent=2))
            return

        # Fallback for accounts where /v2/event-types is not exposed.
        me_response = await client.get(f"{base_url}/me", headers=headers)
        me_payload = _safe_json(me_response)
        me_data = me_payload.get("data", {}) if isinstance(me_payload.get("data"), dict) else {}
        username = str(me_data.get("username") or "").strip()
        if me_response.status_code != 200 or not username:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status_code": response.status_code,
                        "error": payload,
                        "fallback_error": _safe_json(me_response),
                    },
                    indent=2,
                )
            )
            raise SystemExit(1)

        profile_response = await client.get(f"https://cal.com/{username}")
        if profile_response.status_code != 200:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status_code": response.status_code,
                        "error": payload,
                        "fallback_error": {
                            "message": "Failed to fetch public profile for slug extraction.",
                            "profile_status_code": profile_response.status_code,
                        },
                    },
                    indent=2,
                )
            )
            raise SystemExit(1)

        slugs = _extract_slugs(profile_response.text, username)
        valid = await _validate_slug_event_types(
            client=client,
            base_url=base_url,
            headers=headers,
            username=username,
            slugs=slugs,
        )

    print(
        json.dumps(
            {
                "ok": True,
                "source": "slots_fallback",
                "username": username,
                "event_types_endpoint_status_code": response.status_code,
                "count": len(valid),
                "event_types": valid,
                "note": "Numeric eventTypeId values are not discoverable from this account via /v2/event-types.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
