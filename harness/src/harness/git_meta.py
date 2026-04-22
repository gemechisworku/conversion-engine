"""Git revision for reproducibility."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_rev(repo: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo.resolve()),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip().split("\n")[0]
    except Exception:
        return "unknown"
