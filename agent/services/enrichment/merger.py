"""Deterministic enrichment merge pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

from agent.services.enrichment.schemas import EnrichmentArtifact, SignalSnapshot


class EnrichmentPipeline:
    # Implements: FR-2, FR-6
    # Workflow: lead_intake_and_enrichment.md
    # Schema: hiring_signal_brief.md
    # API: research_api.md
    def merge(
        self,
        *,
        company_id: str,
        crunchbase: SignalSnapshot | None,
        job_posts: SignalSnapshot | None,
        layoffs: SignalSnapshot | None,
        leadership_changes: SignalSnapshot | None,
    ) -> EnrichmentArtifact:
        signals: dict[str, SignalSnapshot] = {
            "crunchbase": crunchbase or self._missing_signal(),
            "job_posts": job_posts or self._missing_signal(),
            "layoffs": layoffs or self._missing_signal(),
            "leadership_changes": leadership_changes or self._missing_signal(),
        }
        signals["tech_stack"] = self._tech_stack_signal(crunchbase=signals["crunchbase"])
        merged_confidence = {
            "funding_signal": signals["crunchbase"].confidence,
            "hiring_signal": signals["job_posts"].confidence,
            "layoff_signal": signals["layoffs"].confidence,
            "leadership_signal": signals["leadership_changes"].confidence,
            "tech_stack_signal": signals["tech_stack"].confidence,
        }
        return EnrichmentArtifact(
            company_id=company_id,
            generated_at=datetime.now(UTC),
            signals=signals,
            merged_confidence=merged_confidence,
        )

    @staticmethod
    def _missing_signal() -> SignalSnapshot:
        return SignalSnapshot(summary={"status": "source_unavailable"}, confidence=0.2, source_refs=[])

    @staticmethod
    def _tech_stack_signal(*, crunchbase: SignalSnapshot) -> SignalSnapshot:
        summary = crunchbase.summary if isinstance(crunchbase.summary, dict) else {}
        stack = summary.get("tech_stack") if isinstance(summary, dict) else []
        present = isinstance(stack, list) and len(stack) > 0
        return SignalSnapshot(
            summary={
                "present": present,
                "technologies": stack[:25] if isinstance(stack, list) else [],
            },
            confidence=float(crunchbase.confidence if present else 0.35),
            source_refs=crunchbase.source_refs,
        )
