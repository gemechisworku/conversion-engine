"""Signal enrichment adapters and merger."""

from .crunchbase import CrunchbaseAdapter
from .jobs_playwright import JobsPlaywrightCollector
from .layoffs import LayoffsAdapter
from .leadership import LeadershipChangeDetector
from .merger import EnrichmentPipeline
from .schemas import EnrichmentArtifact, SignalSnapshot

__all__ = [
    "CrunchbaseAdapter",
    "JobsPlaywrightCollector",
    "LayoffsAdapter",
    "LeadershipChangeDetector",
    "EnrichmentPipeline",
    "EnrichmentArtifact",
    "SignalSnapshot",
]

