from __future__ import annotations

import pytest

from harness.split_checks import assert_disjoint_or_raise, sha256_file


def test_disjoint_ok(tmp_path) -> None:
    assert_disjoint_or_raise(["1", "2"], ["3", "4"])


def test_disjoint_raises() -> None:
    with pytest.raises(ValueError, match="Overlapping"):
        assert_disjoint_or_raise(["1", "2"], ["2", "3"])


def test_sha256_file(tmp_path) -> None:
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello")
    h = sha256_file(p)
    assert len(h) == 64
    assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
