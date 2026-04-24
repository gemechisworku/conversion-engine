"""Pytest session defaults."""

from __future__ import annotations

import pytest

from agent.config.logging import configure_logging


@pytest.fixture(scope="session", autouse=True)
def _session_logging() -> None:
    configure_logging()
