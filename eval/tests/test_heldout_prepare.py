from __future__ import annotations

import json

import pytest

from harness.config import BaselineSettings
from harness.heldout_prepare import run_heldout_prepare


def _minimal_settings(
    *,
    tmp_path,
    dev_ids: list[str],
    held_ids: list[str],
    expected_heldout: int = 2,
) -> BaselineSettings:
    dev_p = tmp_path / "dev.json"
    held_p = tmp_path / "held.json"
    dev_p.write_text(json.dumps(dev_ids), encoding="utf-8")
    held_p.write_text(json.dumps(held_ids), encoding="utf-8")
    return BaselineSettings(
        experiment_name="t",
        domain="retail",
        dev_task_ids_path=dev_p,
        heldout_task_ids_path=held_p,
        expected_heldout_count=expected_heldout,
        agent_llm="openrouter/mock",
        user_llm="openrouter/mock",
        tau2_root=tmp_path,
        output_dir=tmp_path / "out",
    )


def test_prepare_writes_manifest(tmp_path) -> None:
    s = _minimal_settings(tmp_path=tmp_path, dev_ids=["0", "1"], held_ids=["2", "3"])
    out = run_heldout_prepare(s)
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["n_heldout_ids"] == 2
    assert "sha256" in data


def test_prepare_rejects_overlap(tmp_path) -> None:
    s = _minimal_settings(tmp_path=tmp_path, dev_ids=["0", "1"], held_ids=["1", "2"])
    with pytest.raises(ValueError, match="Overlapping"):
        run_heldout_prepare(s)


def test_prepare_rejects_wrong_count(tmp_path) -> None:
    s = _minimal_settings(
        tmp_path=tmp_path,
        dev_ids=["0", "1"],
        held_ids=["2"],
        expected_heldout=2,
    )
    with pytest.raises(ValueError, match="Expected 2"):
        run_heldout_prepare(s)
