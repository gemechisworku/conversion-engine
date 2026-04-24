"""Controlled web research (search → fetch → extract); providers are swappable."""

from __future__ import annotations

from agent.services.enrichment.web_research.types import ControlledResearchResult, ExtractedPage, SearchHit

__all__ = ["ControlledResearchResult", "ExtractedPage", "SearchHit"]
