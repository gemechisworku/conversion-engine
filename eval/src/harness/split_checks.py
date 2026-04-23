"""Validate dev / held-out task id splits."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def assert_disjoint_or_raise(a: Iterable[str], b: Iterable[str], *, context: str = "") -> None:
    sa, sb = set(a), set(b)
    inter = sa & sb
    if inter:
        msg = f"Overlapping task ids between splits: {sorted(inter)[:20]}"
        if len(inter) > 20:
            msg += f" … ({len(inter)} total)"
        if context:
            msg = f"{context}: {msg}"
        raise ValueError(msg)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
