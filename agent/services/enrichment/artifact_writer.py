"""Persistence helpers for enrichment evidence artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.config.settings import Settings


class EnrichmentArtifactWriter:
    # Implements: FR-6, FR-15
    # Workflow: lead_intake_and_enrichment.md
    # Schema: hiring_signal_brief.md, competitor_gap_brief.md, ai_maturity_score.md
    # API: research_api.md, scoring_api.md
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    def write_lead_briefs(
        self,
        *,
        lead_id: str,
        hiring_signal_brief: dict[str, Any],
        competitor_gap_brief: dict[str, Any],
        ai_maturity_score: dict[str, Any],
        enrichment_artifact: dict[str, Any],
    ) -> dict[str, str]:
        lead_dir = Path(self._settings.act2_evidence_dir) / lead_id
        lead_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "hiring_signal_brief": hiring_signal_brief,
            "competitor_gap_brief": competitor_gap_brief,
            "ai_maturity_score": ai_maturity_score,
            "enrichment_artifact": enrichment_artifact,
        }
        paths: dict[str, str] = {}
        for name, payload in artifacts.items():
            path = lead_dir / f"{name}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            paths[name] = str(path)
        return paths
