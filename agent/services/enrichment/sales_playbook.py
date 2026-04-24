"""Load Tenacious reference copy from `tenacious_sales_data/` (ICP, tone, sequences, policy)."""

from __future__ import annotations

from pathlib import Path

from agent.config.settings import Settings


def tenacious_sales_data_root(settings: Settings) -> Path:
    raw = (settings.tenacious_sales_data_path or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    # Repo root: agent/services/enrichment -> parents[3]
    return Path(__file__).resolve().parents[3] / "tenacious_sales_data"


def load_sales_playbook_text(*, settings: Settings, relative_path: str, max_chars: int | None = None) -> str:
    path = tenacious_sales_data_root(settings) / relative_path.replace("\\", "/").lstrip("/")
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n\n[truncated for LLM context budget]"
    return text


def load_icp_definition(settings: Settings) -> str:
    return load_sales_playbook_text(settings=settings, relative_path="seed/icp_definition.md")


def load_style_guide(settings: Settings) -> str:
    return load_sales_playbook_text(settings=settings, relative_path="seed/style_guide.md")


def load_cold_email_playbook(settings: Settings) -> str:
    return load_sales_playbook_text(
        settings=settings,
        relative_path="seed/email_sequences/cold.md",
        max_chars=14_000,
    )


def load_acknowledgement_policy(settings: Settings) -> str:
    return load_sales_playbook_text(
        settings=settings,
        relative_path="policy/acknowledgement.md",
        max_chars=4_000,
    )


def load_bench_summary_snippet(settings: Settings) -> str:
    return load_sales_playbook_text(
        settings=settings,
        relative_path="seed/bench_summary.json",
        max_chars=6_000,
    )
