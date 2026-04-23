"""Monotonic ``eval_run_index`` per output dir (fresh run increments; ``--resume`` reuses previous)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)


def allocate_eval_run_index(path: Path, *, resume: bool) -> int:
    """
    Persist ``next_eval_run_index`` in ``path`` (JSON).

    - **Fresh** run: returns current counter value ``n``, then stores ``n + 1``.
    - **Resume**: returns ``n - 1`` (the in-progress run) and **does not** change the file.

    ``n`` is read from ``next_eval_run_index`` (default ``1`` if the file is missing).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, int] = {"next_eval_run_index": 1}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("next_eval_run_index"), int):
                data = {"next_eval_run_index": int(raw["next_eval_run_index"])}
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            _log.warning("eval_run_state: ignoring corrupt %s (%s); resetting counter", path, exc)

    nxt = max(1, int(data["next_eval_run_index"]))
    if resume:
        if nxt <= 1:
            raise ValueError(
                f"Cannot --resume: {path.name} has next_eval_run_index={nxt!r} "
                "(no prior evaluation run to attach to). Run a full invocation first without --resume."
            )
        return nxt - 1

    current = nxt
    data["next_eval_run_index"] = nxt + 1
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return current
