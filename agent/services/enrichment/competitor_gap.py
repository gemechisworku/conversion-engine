"""Competitor gap brief generation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from agent.services.enrichment.ai_maturity import score_ai_maturity
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.config.settings import Settings
from agent.services.enrichment.schemas import (
    AIMaturityScore,
    CompetitorGapBrief,
    CompetitorRecord,
    EnrichmentArtifact,
    PracticeGap,
    SignalSnapshot,
    TopQuartilePractice,
)


class CompetitorGapAnalyst:
    # Implements: FR-4
    # Workflow: lead_intake_and_enrichment.md
    # Schema: competitor_gap_brief.md
    # API: scoring_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        llm: OpenRouterJSONClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._llm = llm

    async def build_brief(
        self,
        *,
        lead_id: str,
        company_id: str,
        artifact: EnrichmentArtifact,
        ai_maturity: AIMaturityScore,
    ) -> CompetitorGapBrief:
        dataset = await self._load_dataset()
        industry = self._industry_from_artifact(artifact)
        peers = self._pick_peers(dataset=dataset, company_id=company_id, industry=industry)
        if len(peers) < 5:
            peers = (peers + self._fallback_peers(dataset=dataset, company_id=company_id))[:10]

        comparisons = [self._to_competitor_record(row=row) for row in peers[:10]]
        competitor_scores = [record.ai_maturity_score for record in comparisons] or [0]
        percentile = self._percentile(value=ai_maturity.score, values=competitor_scores)

        top_practices = self._top_quartile_practices(comparisons=comparisons)
        missing_practices = self._missing_practices(
            artifact=artifact,
            ai_score=ai_maturity.score,
            top_practices=top_practices,
        )
        confidence = 0.75 if len(comparisons) >= 5 else 0.55
        risk_notes: list[str] = []
        if len(comparisons) < 5:
            risk_notes.append("Comparison set smaller than preferred 5-company minimum.")
        if not missing_practices:
            risk_notes.append("No robust missing-practice signal; use exploratory language.")

        deterministic = CompetitorGapBrief(
            gap_brief_id=f"gap_{uuid4().hex[:10]}",
            lead_id=lead_id,
            company_id=company_id,
            comparison_set=comparisons,
            sector_percentile=percentile,
            top_quartile_practices=top_practices,
            missing_practices=missing_practices,
            confidence=confidence,
            risk_notes=risk_notes,
        )
        llm_refined = await self._refine_with_llm(
            deterministic=deterministic,
            artifact=artifact,
            ai_maturity=ai_maturity,
        )
        return llm_refined or deterministic

    async def _load_dataset(self) -> list[dict[str, Any]]:
        if self._settings.crunchbase_dataset_path:
            path = Path(self._settings.crunchbase_dataset_path)
            if path.exists():
                return self._rows_from_file(path=path)
        if self._settings.crunchbase_dataset_url:
            return await self._rows_from_url(url=self._settings.crunchbase_dataset_url)
        return []

    def _rows_from_file(self, *, path: Path) -> list[dict[str, Any]]:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return [payload]
            if isinstance(payload, list):
                return [row for row in payload if isinstance(row, dict)]
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    async def _rows_from_url(self, *, url: str) -> list[dict[str, Any]]:
        if self._http_client is not None:
            response = await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
        else:
            async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
                response = await client.get(url)
        if not response.is_success:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    @staticmethod
    def _industry_from_artifact(artifact: EnrichmentArtifact) -> str:
        crunchbase = artifact.signals.get("crunchbase")
        if crunchbase is None or not isinstance(crunchbase.summary, dict):
            return ""
        return str(crunchbase.summary.get("industry") or "").strip().lower()

    def _pick_peers(
        self,
        *,
        dataset: list[dict[str, Any]],
        company_id: str,
        industry: str,
    ) -> list[dict[str, Any]]:
        peers: list[dict[str, Any]] = []
        for row in dataset:
            if str(row.get("company_id") or row.get("id") or "").strip() == company_id:
                continue
            row_industries = [item.lower() for item in CrunchbaseAdapter._industry_values(row)]
            row_industry = str(row.get("industry") or "").strip().lower()
            if industry and industry not in row_industries and row_industry != industry:
                continue
            peers.append(row)
        return peers

    def _fallback_peers(self, *, dataset: list[dict[str, Any]], company_id: str) -> list[dict[str, Any]]:
        peers: list[dict[str, Any]] = []
        for row in dataset:
            if str(row.get("company_id") or row.get("id") or "").strip() == company_id:
                continue
            peers.append(row)
        return peers

    def _to_competitor_record(self, *, row: dict[str, Any]) -> CompetitorRecord:
        row_company_id = str(row.get("company_id") or row.get("id") or row.get("uuid") or uuid4().hex[:8])
        artifact = self._artifact_from_row(row=row, company_id=row_company_id)
        maturity = score_ai_maturity(company_id=row_company_id, artifact=artifact)
        ai_score = maturity.score
        return CompetitorRecord(
            company_name=str(row.get("company_name") or row.get("name") or "Unknown Company"),
            reason_included="same sector/stage public profile",
            ai_maturity_score=ai_score,
            confidence=maturity.confidence,
        )

    def _artifact_from_row(self, *, row: dict[str, Any], company_id: str) -> EnrichmentArtifact:
        industries = CrunchbaseAdapter._industry_values(row)
        tech_stack = CrunchbaseAdapter._tech_stack(row=row)
        funding_events = CrunchbaseAdapter._funding_events(row=row, lookback_days=180)
        ai_roles = self._coerce_int(row.get("ai_roles") or row.get("ml_roles"))
        engineering_roles = self._coerce_int(row.get("engineering_roles") or row.get("job_posts"))
        if engineering_roles == 0 and ai_roles > 0:
            engineering_roles = ai_roles
        return EnrichmentArtifact(
            company_id=company_id,
            signals={
                "crunchbase": SignalSnapshot(
                    summary={
                        "company_id": company_id,
                        "company_name": row.get("company_name") or row.get("name"),
                        "industry": industries[0] if industries else "",
                        "industries": industries,
                        "funding_round": row.get("funding_round"),
                        "funding_events_180d": funding_events,
                        "tech_stack": tech_stack,
                    },
                    confidence=0.78,
                ),
                "job_posts": SignalSnapshot(
                    summary={
                        "engineering_role_count": engineering_roles,
                        "ai_adjacent_role_count": ai_roles,
                        "role_titles": [],
                        "source_urls": [],
                        "window_days": 60,
                    },
                    confidence=0.45 if engineering_roles == 0 else 0.65,
                ),
                "layoffs": SignalSnapshot(summary={"matched": False, "window_days": 120}, confidence=0.45),
                "leadership_changes": SignalSnapshot(summary={"matched": False, "window_days": 90}, confidence=0.45),
                "tech_stack": SignalSnapshot(
                    summary={"present": bool(tech_stack), "technologies": tech_stack},
                    confidence=0.65 if tech_stack else 0.35,
                ),
            },
            merged_confidence={},
        )

    @staticmethod
    def _percentile(*, value: int, values: list[int]) -> float:
        if not values:
            return 0.0
        less_or_equal = sum(1 for item in values if item <= value)
        return round(less_or_equal / len(values), 2)

    @staticmethod
    def _top_quartile_practices(*, comparisons: list[CompetitorRecord]) -> list[TopQuartilePractice]:
        if not comparisons:
            return []
        ranked = sorted(comparisons, key=lambda item: item.ai_maturity_score, reverse=True)
        top_count = max(1, len(ranked) // 4)
        top_slice = ranked[:top_count]
        if any(item.ai_maturity_score >= 2 for item in top_slice):
            return [
                TopQuartilePractice(
                    practice="Dedicated AI/ML or data-platform hiring signal in public roles.",
                    evidence_refs=["competitor_set"],
                ),
                TopQuartilePractice(
                    practice="Consistent funding and hiring momentum alignment.",
                    evidence_refs=["competitor_set"],
                ),
                TopQuartilePractice(
                    practice="Public technology profile shows modern data or automation tooling.",
                    evidence_refs=["competitor_set"],
                ),
            ]
        return [
            TopQuartilePractice(
                practice="Public signal suggests structured engineering growth pattern.",
                evidence_refs=["competitor_set"],
            )
        ]

    @staticmethod
    def _missing_practices(
        *,
        artifact: EnrichmentArtifact,
        ai_score: int,
        top_practices: list[TopQuartilePractice],
    ) -> list[PracticeGap]:
        jobs = artifact.signals.get("job_posts")
        jobs_summary = jobs.summary if jobs and isinstance(jobs.summary, dict) else {}
        ai_roles = int(jobs_summary.get("ai_adjacent_role_count") or 0)
        missing: list[PracticeGap] = []
        if ai_roles == 0 and top_practices:
            missing.append(
                PracticeGap(
                    practice="No public AI-adjacent hiring signal despite peer top-quartile pattern.",
                    confidence=0.72,
                    evidence_refs=["jobs_signal", "competitor_set"],
                )
            )
        if ai_score <= 1:
            missing.append(
                PracticeGap(
                    practice="AI maturity appears early-stage relative to peer set.",
                    confidence=0.66,
                    evidence_refs=["ai_maturity", "competitor_set"],
                )
            )
        if len(missing) < 3 and top_practices:
            missing.append(
                PracticeGap(
                    practice="No strong public evidence of the peer group's modern data/automation tooling pattern.",
                    confidence=0.58,
                    evidence_refs=["crunchbase_signal", "competitor_set"],
                )
            )
        return missing

    async def _refine_with_llm(
        self,
        *,
        deterministic: CompetitorGapBrief,
        artifact: EnrichmentArtifact,
        ai_maturity: AIMaturityScore,
    ) -> CompetitorGapBrief | None:
        if self._llm is None or not self._llm.configured:
            return None
        candidate = await self._llm.generate_model(
            system_prompt=(
                "You are the Competitor Gap Analyst. Refine the deterministic competitor_gap_brief "
                "without inventing competitors, practices, or evidence refs. Keep 5-10 competitors when supplied, "
                "avoid condescension, and frame gaps as public-signal observations."
            ),
            user_payload={
                "required_schema": CompetitorGapBrief.model_json_schema(),
                "deterministic_candidate": deterministic.model_dump(mode="json"),
                "prospect_evidence": artifact.model_dump(mode="json"),
                "prospect_ai_maturity": ai_maturity.model_dump(mode="json"),
            },
            response_model=CompetitorGapBrief,
        )
        if not isinstance(candidate, CompetitorGapBrief):
            return None
        if candidate.lead_id != deterministic.lead_id or candidate.company_id != deterministic.company_id:
            return None
        if not (5 <= len(candidate.comparison_set) <= 10):
            return None
        candidate.sector_percentile = float(max(0.0, min(1.0, candidate.sector_percentile)))
        candidate.confidence = float(max(0.0, min(1.0, candidate.confidence)))
        return candidate

    @staticmethod
    def _coerce_int(value: Any) -> int:
        if value in (None, ""):
            return 0
        try:
            return int(str(value).replace(",", "").strip())
        except ValueError:
            return 0
