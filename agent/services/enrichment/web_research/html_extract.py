"""Extract human-readable text and title from HTML (single-page, depth 0)."""

from __future__ import annotations

import re
from html import unescape


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_html(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", value))


def extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return strip_html(unescape(match.group(1)))[:200] or None
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    return strip_html(unescape(heading.group(1)))[:200] if heading else None


def extract_meta_description(html: str) -> str | None:
    meta = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if meta:
        return strip_html(unescape(meta.group(1)))[:400] or None
    return None


def extract_main_text(html: str, *, max_chars: int = 12000) -> str:
    """Cheap readability: strip scripts/styles then visible text."""
    without_scripts = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    without_styles = re.sub(r"<style[^>]*>.*?</style>", " ", without_scripts, flags=re.IGNORECASE | re.DOTALL)
    text = strip_html(unescape(without_styles))
    return text[:max_chars] if text else ""


def is_blocked_or_low_signal(html: str) -> bool:
    lowered = html.lower()
    markers = [
        "attention required! | cloudflare",
        "sorry, you have been blocked",
        "please enable cookies",
        "cf-error-code",
        "enable javascript and cookies to continue",
        "access denied",
    ]
    return any(marker in lowered for marker in markers)
