from __future__ import annotations

import asyncio

from agent.services.enrichment.hiring_brief import build_hiring_signal_brief_with_llm
from agent.services.enrichment.schemas import (
    AIMaturityScore,
    EnrichmentArtifact,
    ICPClassification,
    SignalSnapshot,
)


class _LLMStub:
    configured = True

    async def generate_model(self, **kwargs):
        response_model = kwargs["response_model"]
        deterministic = kwargs["user_payload"]["deterministic_candidate"]
        candidate = response_model.model_validate(deterministic)
        candidate.primary_segment_hypothesis = "segment_4_specialized_capability"
        candidate.alternate_segment_hypothesis = "segment_1_series_a_b"
        candidate.segment_confidence = 0.91
        candidate.risk_notes = []
        return candidate


def test_hiring_brief_keeps_classifier_segment_fields_even_after_llm_refinement() -> None:
    artifact = EnrichmentArtifact(
        company_id="comp_1",
        signals={
            "crunchbase": SignalSnapshot(summary={"funding_round": "Series A"}, confidence=0.9),
            "job_posts": SignalSnapshot(
                summary={"engineering_role_count": 8, "ai_adjacent_role_count": 1, "role_titles": []},
                confidence=0.8,
            ),
            "layoffs": SignalSnapshot(summary={"matched": False}, confidence=0.7),
            "leadership_changes": SignalSnapshot(summary={"matched": False}, confidence=0.7),
            "tech_stack": SignalSnapshot(summary={"technologies": ["python"]}, confidence=0.7),
        },
        merged_confidence={},
    )
    ai = AIMaturityScore(
        score_id="score_1",
        company_id="comp_1",
        score=1,
        confidence=0.72,
    )
    classification = ICPClassification(
        classification_id="class_1",
        primary_segment="abstain",
        alternate_segment=None,
        confidence=0.42,
        abstain=True,
        rationale=["Low confidence."],
    )

    brief = asyncio.run(
        build_hiring_signal_brief_with_llm(
            lead_id="lead_1",
            company_id="comp_1",
            artifact=artifact,
            ai_maturity=ai,
            classification=classification,
            llm=_LLMStub(),
        )
    )

    assert brief.primary_segment_hypothesis == "abstain"
    assert brief.alternate_segment_hypothesis is None
    assert brief.segment_confidence == 0.42
    assert "Classification abstained due to low segment confidence." in brief.risk_notes
