from __future__ import annotations

from harness.trace_payload import (
    DEFAULT_TRACE_EXPORT_MAX_CHARS,
    build_trace_simulation_field,
    truncate_simulation_for_export,
)


def test_truncate_unchanged_when_small() -> None:
    d = {"id": "1", "task_id": "t", "x": "hi"}
    out = truncate_simulation_for_export(d, max_chars=10_000)
    assert out is d
    assert out["x"] == "hi"


def test_truncate_stub_when_huge() -> None:
    d = {"id": "run", "task_id": "7", "reward_info": {"reward": 1.0}, "blob": "x" * 200_000}
    out = truncate_simulation_for_export(d, max_chars=1000)
    assert out["_truncated"] is True
    assert out["id"] == "run"


def test_build_full_is_deepcopy() -> None:
    d = {"a": [1, 2]}
    out = build_trace_simulation_field(
        d, mode="full", max_chars=DEFAULT_TRACE_EXPORT_MAX_CHARS
    )
    assert out == d
    assert out is not d
    out["a"].append(3)
    assert len(d["a"]) == 2


def test_build_compact_matches_truncate() -> None:
    d = {"k": "v"}
    a = truncate_simulation_for_export(d, max_chars=500)
    b = build_trace_simulation_field(d, mode="compact", max_chars=500)
    assert a == b
