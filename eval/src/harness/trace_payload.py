"""Shared simulation JSON for ``trace_log.jsonl`` and Langfuse span output."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal

TraceSimulationPayloadMode = Literal["compact", "full"]

# Match Langfuse span output budget unless YAML overrides.
DEFAULT_TRACE_EXPORT_MAX_CHARS = 120_000


def truncate_simulation_for_export(
    obj: dict[str, Any],
    *,
    max_chars: int = DEFAULT_TRACE_EXPORT_MAX_CHARS,
) -> dict[str, Any]:
    """
    If JSON serialization exceeds ``max_chars``, return a small stub dict.
    Otherwise return ``obj`` unchanged (same reference).
    """
    raw = json.dumps(obj, default=str)
    if len(raw) <= max_chars:
        return obj
    return {
        "_truncated": True,
        "_original_chars": len(raw),
        "task_id": obj.get("task_id"),
        "id": obj.get("id"),
        "reward_info": obj.get("reward_info"),
        "termination_reason": str(obj.get("termination_reason", "")),
        "note": (
            "Payload exceeded trace_export_max_chars. "
            "Set trace_simulation_payload: full in baseline.yaml for full local JSONL "
            "(Langfuse may still cap very large payloads server-side)."
        ),
    }


def build_trace_simulation_field(
    sim_dump: dict[str, Any],
    *,
    mode: TraceSimulationPayloadMode,
    max_chars: int,
) -> dict[str, Any]:
    """``full`` → deep copy of dump; ``compact`` → same truncation rules as Langfuse."""
    if mode == "full":
        return deepcopy(sim_dump)
    return truncate_simulation_for_export(sim_dump, max_chars=max_chars)
