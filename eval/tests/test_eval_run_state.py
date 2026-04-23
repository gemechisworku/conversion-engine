import json
from pathlib import Path

from harness.eval_run_state import allocate_eval_run_index


def test_allocate_fresh_increments(tmp_path: Path):
    p = tmp_path / "state.json"
    assert allocate_eval_run_index(p, resume=False) == 1
    assert allocate_eval_run_index(p, resume=False) == 2
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["next_eval_run_index"] == 3


def test_allocate_resume_reuses_without_increment(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"next_eval_run_index": 4}) + "\n", encoding="utf-8")
    assert allocate_eval_run_index(p, resume=True) == 3
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["next_eval_run_index"] == 4


def test_allocate_resume_rejects_when_no_prior(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"next_eval_run_index": 1}) + "\n", encoding="utf-8")
    try:
        allocate_eval_run_index(p, resume=True)
    except ValueError as e:
        assert "Cannot --resume" in str(e)
    else:
        raise AssertionError("expected ValueError")
