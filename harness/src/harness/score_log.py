"""Read / merge / write score_log.json (schema v1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"


def load_or_init(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "experiments": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid score log: {path}")
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("experiments", [])
    return data


def append_experiment(path: Path, experiment: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_or_init(path)
    data["experiments"].append(experiment)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
