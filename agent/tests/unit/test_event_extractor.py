from __future__ import annotations

from datetime import UTC, datetime

from agent.services.enrichment.event_extractor import EventExtractor


def test_event_extractor_normalize_collects_configured_fields() -> None:
    extractor = EventExtractor()
    row = {
        "funding_rounds_list": '[{"investment_type":"Series A","announced_on":"2025-11-01","money_raised":{"value_usd":5000000}}]',
        "news": '[{"date":"2025-11-02","title":"Company raises Series B","url":"https://example.com/news"}]',
        "about": "Company builds AI software",
    }
    candidates = extractor.normalize(row=row, source_url="https://www.crunchbase.com/organization/demo")
    fields = {candidate.source_field for candidate in candidates}

    assert "funding_rounds_list" in fields
    assert "news" in fields
    assert "about" in fields


def test_event_extractor_extracts_structured_funding_with_date_and_amount() -> None:
    extractor = EventExtractor()
    row = {
        "funding_rounds_list": '[{"investment_type":"Series A","announced_on":"2025-11-01","money_raised":{"value_usd":5000000}}]',
    }
    candidates = extractor.normalize(row=row)
    events = extractor.extract_funding_events(candidates=candidates)
    recent = extractor.events_within_days(
        events=events,
        days=180,
        reference_now=datetime(2025, 11, 15, tzinfo=UTC),
    )

    assert len(recent) == 1
    event = recent[0]
    assert event.event_category == "funding"
    assert event.event_type == "Series A"
    assert event.event_date == "2025-11-01"
    assert float(event.extracted_values.get("amount")) == 5000000.0
    assert event.confidence >= 0.7


def test_event_extractor_rejects_funding_without_date_under_threshold() -> None:
    extractor = EventExtractor()
    row = {
        "financials_highlights": '{"funding_total_usd":12000000}',
        "about": "Historically raised funding over time.",
    }
    candidates = extractor.normalize(row=row)
    events = extractor.extract_funding_events(candidates=candidates)

    assert events == []


def test_event_extractor_extracts_layoff_from_structured_field() -> None:
    extractor = EventExtractor()
    row = {
        "layoff": '[{"key_event_date":"2025-10-25","affected_count":120,"affected_percent":15,"label":"Company laid off 120 employees"}]'
    }
    candidates = extractor.normalize(row=row)
    events = extractor.extract_layoff_events(candidates=candidates)
    recent = extractor.events_within_days(
        events=events,
        days=120,
        reference_now=datetime(2025, 11, 15, tzinfo=UTC),
    )

    assert len(recent) == 1
    event = recent[0]
    assert event.event_category == "layoff"
    assert event.event_date == "2025-10-25"
    assert event.extracted_values["affected_count"] == 120
    assert event.confidence >= 0.7


def test_event_extractor_extracts_recent_leadership_appointment() -> None:
    extractor = EventExtractor()
    row = {
        "leadership_hire": '[{"key_event_date":"2025-10-20","label":"Acme appoints Jane Doe as Chief Technology Officer","person":"Jane Doe","role_name":"Chief Technology Officer","link":"https://example.com/pr"}]'
    }
    candidates = extractor.normalize(row=row)
    events = extractor.extract_leadership_events(candidates=candidates)
    recent = extractor.events_within_days(
        events=events,
        days=90,
        reference_now=datetime(2025, 11, 15, tzinfo=UTC),
    )

    assert len(recent) == 1
    event = recent[0]
    assert event.event_category == "leadership_change"
    assert "technology officer" in str(event.extracted_values.get("role", "")).lower()
    assert event.extracted_values.get("person_name") == "Jane Doe"
    assert event.confidence >= 0.7
