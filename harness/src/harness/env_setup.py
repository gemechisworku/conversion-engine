"""Configure process environment before importing tau2 (DATA_DIR, .env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def setup_tau2_environment(*, tau2_root: Path) -> None:
    """
    Must run before any `import tau2`.

    - Sets TAU2_DATA_DIR to `<tau2_root>/data` so tasks load regardless of CWD.
    - Loads `<tau2_root>/.env` for API keys (OpenRouter, etc.).
    """
    tau2_root = tau2_root.resolve()
    data_dir = tau2_root / "data"
    os.environ["TAU2_DATA_DIR"] = str(data_dir)
    env_file = tau2_root / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)
