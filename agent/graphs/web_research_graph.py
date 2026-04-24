"""LangGraph entry for controlled web research (delegates to services)."""

from __future__ import annotations

from agent.services.enrichment.web_research.runner import (
    ControlledWebResearchRunner,
    ResearchDeps,
    build_research_runner,
)

__all__ = ["ControlledWebResearchRunner", "ResearchDeps", "build_research_runner"]
