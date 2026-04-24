from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field
from typing_extensions import NotRequired


class SearchHit(BaseModel):
    model_config = {"extra": "forbid"}

    title: str | None = None
    url: str
    snippet: str | None = None
    provider: str


class ExtractedPage(BaseModel):
    model_config = {"extra": "forbid"}

    url: str
    title: str | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    fetch_error: str | None = None


class RankedPage(BaseModel):
    model_config = {"extra": "forbid"}

    url: str
    title: str | None = None
    summary: str
    relevance: float
    body_excerpt: str


class ControlledResearchResult(BaseModel):
    model_config = {"extra": "forbid"}

    synthesis: str
    source_urls: list[str]
    ranked_pages: list[RankedPage] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ResearchGraphState(TypedDict, total=False):
    # Implements: FR-2, FR-4
    # Workflow: lead_intake_and_enrichment.md, reply_handling.md
    user_query: str
    max_search_results: int
    max_depth: NotRequired[int]
    per_page_timeout_seconds: float
    mode: NotRequired[Literal["news", "competitor", "generic"]]
    seed_urls: NotRequired[list[str]]

    search_hits: list[dict[str, Any]]
    extracted_pages: list[dict[str, Any]]
    ranked_pages: list[dict[str, Any]]
    synthesis: str
    source_urls: list[str]
    errors: Annotated[list[str], add]
