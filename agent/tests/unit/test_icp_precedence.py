from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent.services.enrichment.icp_classifier import classify_icp
from agent.services.enrichment.schemas import AIMaturityScore, EnrichmentArtifact, SignalSnapshot


def test_icp_precedence_cto_transition_beats_series_a() -> None:
    """Rule 2 in seed/icp_definition.md: leadership transition window dominates fresh funding."""
    now = datetime.now(UTC)
    fund_dt = (now - timedelta(days=45)).isoformat()
    lead_dt = (now - timedelta(days=25)).isoformat()
    artifact = EnrichmentArtifact(
        company_id="comp_x",
        generated_at=now,
        signals={
            "crunchbase": SignalSnapshot(
                summary={
                    "funding_round": "Series A",
                    "funding_date": fund_dt,
                },
                confidence=0.9,
            ),
            "job_posts": SignalSnapshot(
                summary={"engineering_role_count": 9, "ai_adjacent_role_count": 1},
                confidence=0.85,
            ),
            "layoffs": SignalSnapshot(summary={"matched": False}, confidence=0.7),
            "leadership_changes": SignalSnapshot(
                summary={"matched": True, "role_name": "CTO", "date": lead_dt},
                confidence=0.85,
            ),
        },
        merged_confidence={},
    )
    score = AIMaturityScore(
        score_id="s1",
        company_id="comp_x",
        score=2,
        confidence=0.75,
        generated_at=now,
    )
    c = classify_icp(artifact=artifact, ai_maturity=score)
    assert c.primary_segment == "segment_3_leadership_transition"
    assert not c.abstain


def test_icp_layoff_plus_funding_forces_segment_2() -> None:
    now = datetime.now(UTC)
    fund_dt = (now - timedelta(days=40)).isoformat()
    layoff_dt = (now - timedelta(days=18)).isoformat()
    artifact = EnrichmentArtifact(
        company_id="comp_y",
        generated_at=now,
        signals={
            "crunchbase": SignalSnapshot(
                summary={
                    "funding_round": "Series B",
                    "funding_date": fund_dt,
                },
                confidence=0.9,
            ),
            "job_posts": SignalSnapshot(
                summary={"engineering_role_count": 6, "ai_adjacent_role_count": 0},
                confidence=0.8,
            ),
            "layoffs": SignalSnapshot(
                summary={
                    "matched": True,
                    "layoff_date": layoff_dt,
                    "affected_percent": 12.0,
                },
                confidence=0.88,
            ),
            "leadership_changes": SignalSnapshot(summary={"matched": False}, confidence=0.5),
        },
        merged_confidence={},
    )
    score = AIMaturityScore(
        score_id="s2",
        company_id="comp_y",
        score=1,
        confidence=0.6,
        generated_at=now,
    )
    c = classify_icp(artifact=artifact, ai_maturity=score)
    assert c.primary_segment == "segment_2_mid_market_restructure"


def test_icp_uses_funding_events_when_funding_round_fields_missing() -> None:
    now = datetime.now(UTC)
    event_dt = (now - timedelta(days=20)).date().isoformat()
    artifact = EnrichmentArtifact(
        company_id="comp_z",
        generated_at=now,
        signals={
            "crunchbase": SignalSnapshot(
                summary={
                    "funding_round": None,
                    "funding_date": None,
                    "funding_events_180d": [
                        {
                            "round": "Series A",
                            "announced_on": event_dt,
                            "amount_usd": 12000000,
                        }
                    ],
                },
                confidence=0.9,
            ),
            "job_posts": SignalSnapshot(
                summary={"engineering_role_count": 7, "ai_adjacent_role_count": 1},
                confidence=0.82,
            ),
            "layoffs": SignalSnapshot(summary={"matched": False}, confidence=0.7),
            "leadership_changes": SignalSnapshot(summary={"matched": False}, confidence=0.5),
        },
        merged_confidence={},
    )
    score = AIMaturityScore(
        score_id="s3",
        company_id="comp_z",
        score=1,
        confidence=0.7,
        generated_at=now,
    )
    c = classify_icp(artifact=artifact, ai_maturity=score)
    assert c.primary_segment == "segment_1_series_a_b"
    assert c.abstain is False
