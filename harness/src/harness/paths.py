"""Resolve paths relative to config file or explicit roots."""

from __future__ import annotations

from pathlib import Path


def resolve_path(raw: str | Path, *, base: Path) -> Path:
    """Resolve `raw` as absolute or relative to `base` (typically config file dir)."""
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (base / p).resolve()
