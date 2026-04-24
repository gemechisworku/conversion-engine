"""Spec-first orchestration runtime.

`OrchestrationRuntime` is loaded lazily so submodules (e.g. `outreach_pipeline`) can be
imported without pulling the full LangGraph stack (avoids cycles with `lead_intake_langgraph`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.services.orchestration.runtime import OrchestrationRuntime

__all__ = ["OrchestrationRuntime"]


def __getattr__(name: str):
    if name == "OrchestrationRuntime":
        from agent.services.orchestration.runtime import OrchestrationRuntime

        return OrchestrationRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
