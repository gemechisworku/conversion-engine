"""Validate held-out id file and emit a local manifest (no τ-bench runs)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from harness.config import BaselineSettings, load_task_id_list
from harness.split_checks import assert_disjoint_or_raise, sha256_file


def run_heldout_prepare(settings: BaselineSettings) -> Path:
    """
    Verify ``heldout_task_ids_path`` exists, is a JSON id list, optional disjointness vs dev,
    and write ``heldout_prepare_manifest.json`` under ``output_dir``.
    """
    if settings.heldout_task_ids_path is None:
        raise ValueError(
            "heldout_task_ids_path is not set in baseline.yaml — add it to run held-out prepare."
        )
    path = settings.heldout_task_ids_path
    if not path.is_file():
        raise FileNotFoundError(f"Held-out task id file not found: {path}")

    ids = load_task_id_list(path)
    n_exp = settings.expected_heldout_count
    if len(ids) != n_exp:
        raise ValueError(f"Expected {n_exp} held-out task ids, got {len(ids)} in {path}")
    if len(set(ids)) != len(ids):
        raise ValueError(f"Duplicate task ids in held-out list: {path}")

    dev_ids: Optional[list[str]] = None
    if settings.dev_task_ids_path.is_file():
        dev_ids = load_task_id_list(settings.dev_task_ids_path)
        assert_disjoint_or_raise(dev_ids, ids, context="dev vs held-out")

    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "heldout_task_ids_path": str(path.resolve()),
        "n_heldout_ids": len(ids),
        "sha256": sha256_file(path),
        "dev_disjoint": dev_ids is not None,
    }
    out = settings.output_dir / "heldout_prepare_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out
