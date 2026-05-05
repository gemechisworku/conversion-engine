"""Neutral event extraction for enrichment signals.

Implements a three-pass pipeline:
1) normalize heterogeneous source fields into common candidates
2) extract neutral event records (funding, layoff, leadership_change)
3) score and filter candidates by confidence threshold
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

EventCategory = Literal["funding", "layoff", "leadership_change"]
SourceStrength = Literal["structured", "news", "inferred"]

_DATE_PATTERN = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
_FUNDING_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"\bseries\s+a\b", "Series A"),
    (r"\bseries\s+b\b", "Series B"),
    (r"\bseries\s+c\b", "Series C"),
    (r"\bseed(\s+extension)?\b", "Seed"),
    (r"\bseries\s+extension\b", "Series Extension"),
    (r"\bventure\s+round\b", "Venture Round"),
    (r"\bstrategic\s+round\b", "Strategic Round"),
]
_LAYOFF_EVENT_PATTERNS: list[tuple[str, str]] = [
    (r"\blaid\s+off\b", "layoff"),
    (r"\blayoff\b", "layoff"),
    (r"\bworkforce\s+reduction\b", "workforce_reduction"),
    (r"\breduction\s+in\s+force\b", "workforce_reduction"),
    (r"\brif\b", "workforce_reduction"),
    (r"\bjob\s+cuts\b", "layoff"),
    (r"\bdownsizing\b", "layoff"),
    (r"\brestructuring\b", "restructuring"),
    (r"\bheadcount\s+reduction\b", "workforce_reduction"),
    (r"\bcost\s+cutting\b", "restructuring"),
]
_LAYOFF_NEGATIVE_PATTERNS = (
    r"\blayoff\s+prevention\b",
    r"\bcost\s+optimization\b",
)
_LEADERSHIP_ROLE_PATTERN = re.compile(
    r"(?i)\b("
    r"cto|chief\s+technology\s+officer|vp\s+engineering|vp\s+of\s+engineering|head\s+of\s+engineering|"
    r"svp\s+engineering|chief\s+product\s+officer|vp\s+product|head\s+of\s+product|"
    r"chief\s+data\s+officer|chief\s+ai\s+officer"
    r")\b"
)
_LEADERSHIP_VERB_PATTERN = re.compile(
    r"(?i)\b(appointed|appoints|named|joined|hired|promoted|became|steps\s+in\s+as|announced\s+as|welcomed)\b"
)


@dataclass(slots=True)
class NormalizedCandidate:
    source_field: str
    raw_text: str
    raw_json: Any
    source_url: str | None
    event_hint: str
    candidate_date: str | None


@dataclass(slots=True)
class EventRecord:
    event_category: EventCategory
    event_type: str
    event_date: str | None
    confidence: float
    evidence_fields: list[str]
    raw_supporting_text: str
    extracted_values: dict[str, Any]
    source_strength: SourceStrength
    source_url: str | None


class EventExtractor:
    """Three-pass extraction pipeline for noisy enrichment source fields."""

    NORMALIZED_FIELDS = (
        "funding_rounds",
        "funding_rounds_list",
        "funds_raised",
        "financials_highlights",
        "overview_highlights",
        "news",
        "layoff",
        "leadership_hire",
        "current_employees",
        "people_highlights",
        "full_description",
        "about",
    )

    def normalize(self, *, row: dict[str, Any], source_url: str | None = None) -> list[NormalizedCandidate]:
        candidates: list[NormalizedCandidate] = []
        for field in self.NORMALIZED_FIELDS:
            raw_value = row.get(field)
            raw_json = self._jsonish(raw_value)
            raw_text = self._to_text(raw_value, raw_json=raw_json)
            if not raw_text and raw_json in (None, {}, []):
                continue
            candidate_date = self._best_date(raw_json) or self._best_date(raw_text)
            candidates.append(
                NormalizedCandidate(
                    source_field=field,
                    raw_text=raw_text,
                    raw_json=raw_json,
                    source_url=source_url,
                    event_hint=self._event_hint_for_field(field),
                    candidate_date=candidate_date,
                )
            )
        return candidates

    def extract_funding_events(
        self,
        *,
        candidates: list[NormalizedCandidate],
        min_confidence: float = 0.7,
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        for candidate in candidates:
            if candidate.source_field in {"funding_rounds_list", "funding_rounds"}:
                events.extend(self._extract_structured_funding(candidate))
            elif candidate.source_field in {"financials_highlights", "overview_highlights", "news"}:
                maybe = self._extract_text_funding(candidate)
                if maybe is not None:
                    events.append(maybe)
        return self._filter_ranked(events, min_confidence=min_confidence)

    def extract_layoff_events(
        self,
        *,
        candidates: list[NormalizedCandidate],
        min_confidence: float = 0.7,
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        for candidate in candidates:
            if candidate.source_field == "layoff":
                events.extend(self._extract_structured_layoff(candidate))
                continue
            if candidate.source_field not in {"news", "overview_highlights", "full_description"}:
                continue
            maybe = self._extract_text_layoff(candidate)
            if maybe is not None:
                events.append(maybe)
        return self._filter_ranked(events, min_confidence=min_confidence)

    def extract_leadership_events(
        self,
        *,
        candidates: list[NormalizedCandidate],
        min_confidence: float = 0.7,
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        for candidate in candidates:
            if candidate.source_field in {"leadership_hire", "current_employees", "people_highlights"}:
                events.extend(self._extract_structured_leadership(candidate))
                continue
            if candidate.source_field != "news":
                continue
            maybe = self._extract_text_leadership(candidate)
            if maybe is not None:
                events.append(maybe)
        return self._filter_ranked(events, min_confidence=min_confidence)

    def events_within_days(
        self,
        *,
        events: list[EventRecord],
        days: int,
        reference_now: datetime,
    ) -> list[EventRecord]:
        cutoff = reference_now.astimezone(UTC).timestamp() - (days * 86400)
        kept: list[EventRecord] = []
        for event in events:
            dt = self._parse_dt(event.event_date or "")
            if dt is None:
                continue
            if dt.timestamp() >= cutoff:
                kept.append(event)
        kept.sort(key=lambda item: item.event_date or "", reverse=True)
        return kept

    def _extract_structured_funding(self, candidate: NormalizedCandidate) -> list[EventRecord]:
        parsed = candidate.raw_json
        rows: list[Any]
        if isinstance(parsed, list):
            rows = parsed
        elif isinstance(parsed, dict):
            rows = parsed.get("items") if isinstance(parsed.get("items"), list) else [parsed]
        else:
            rows = []
        results: list[EventRecord] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            event_date = (
                self._clean_text(item.get("announced_on"))
                or self._clean_text(item.get("announced_date"))
                or self._clean_text(item.get("date"))
                or self._clean_text(item.get("funded_on"))
            )
            round_name = self._funding_round_name(item)
            if not round_name:
                continue
            amount = self._nested_amount_usd(item)
            record = EventRecord(
                event_category="funding",
                event_type=round_name,
                event_date=event_date or None,
                confidence=self._score(
                    event_type_found=True,
                    has_date=bool(event_date),
                    is_structured=True,
                    has_supporting=True,
                    has_value=amount is not None,
                    vague=False,
                    contradictory=False,
                ),
                evidence_fields=[candidate.source_field],
                raw_supporting_text=candidate.raw_text[:600],
                extracted_values={
                    "amount": amount,
                    "currency": "USD" if amount is not None else None,
                    "investors": self._as_list(item.get("investors")),
                    "lead_investors": self._as_list(item.get("lead_investors")),
                    "round_title": round_name,
                },
                source_strength="structured",
                source_url=self._clean_text(item.get("url") or item.get("link")) or candidate.source_url,
            )
            results.append(record)
        return results

    def _extract_text_funding(self, candidate: NormalizedCandidate) -> EventRecord | None:
        text = candidate.raw_text.lower()
        round_name = ""
        for pattern, label in _FUNDING_TYPE_PATTERNS:
            if re.search(pattern, text):
                round_name = label
                break
        has_funding_phrase = any(token in text for token in ("funding", "raised", "raises", "raise", "venture"))
        if not round_name and not has_funding_phrase:
            return None
        event_date = candidate.candidate_date
        amount = self._first_usd_amount(candidate.raw_text)
        vague = not round_name and not has_funding_phrase
        has_supporting = candidate.source_field == "news"
        inferred_type = round_name or "funding_event"
        if not round_name and candidate.source_field == "news":
            if any(token in text for token in ("prnewswire", "press release", "businesswire", "globenewswire")):
                inferred_type = "press_release_funding"
        source_url = self._candidate_source_url(candidate)
        return EventRecord(
            event_category="funding",
            event_type=inferred_type,
            event_date=event_date,
            confidence=self._score(
                event_type_found=bool(round_name or has_funding_phrase),
                has_date=bool(event_date),
                is_structured=False,
                has_supporting=has_supporting,
                has_value=amount is not None,
                vague=vague,
                contradictory=False,
            ),
            evidence_fields=[candidate.source_field],
            raw_supporting_text=candidate.raw_text[:600],
            extracted_values={
                "amount": amount,
                "currency": "USD" if amount is not None else None,
                "investors": [],
                "lead_investors": [],
                "round_title": inferred_type,
            },
            source_strength="news" if has_supporting else "inferred",
            source_url=source_url,
        )

    def _extract_structured_layoff(self, candidate: NormalizedCandidate) -> list[EventRecord]:
        parsed = candidate.raw_json
        items: list[Any] = parsed if isinstance(parsed, list) else [parsed] if isinstance(parsed, dict) else []
        results: list[EventRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            event_date = (
                self._clean_text(item.get("date"))
                or self._clean_text(item.get("announced_on"))
                or self._clean_text(item.get("layoff_date"))
                or self._clean_text(item.get("key_event_date"))
            )
            affected_count = self._coerce_int(item.get("laid_off") or item.get("affected_count"))
            affected_pct = self._coerce_float(item.get("%") or item.get("affected_percent"))
            raw_blob = f"{item.get('label') or ''} {item.get('title') or ''}".lower()
            event_type = "restructuring" if "restructur" in raw_blob else "layoff"
            results.append(
                EventRecord(
                    event_category="layoff",
                    event_type=event_type,
                    event_date=event_date or None,
                    confidence=self._score(
                        event_type_found=True,
                        has_date=bool(event_date),
                        is_structured=True,
                        has_supporting=bool(item.get("link") or item.get("label")),
                        has_value=(affected_count is not None or affected_pct is not None),
                        vague=False,
                        contradictory=False,
                    ),
                    evidence_fields=[candidate.source_field],
                    raw_supporting_text=candidate.raw_text[:600],
                    extracted_values={
                        "affected_count": affected_count,
                        "affected_pct": affected_pct,
                        "departments": [],
                        "locations": [],
                    },
                    source_strength="structured",
                    source_url=self._clean_text(item.get("link")) or candidate.source_url,
                )
            )
        return results

    def _extract_text_layoff(self, candidate: NormalizedCandidate) -> EventRecord | None:
        text = candidate.raw_text.lower()
        if any(re.search(pattern, text) for pattern in _LAYOFF_NEGATIVE_PATTERNS):
            return None
        event_type = ""
        for pattern, label in _LAYOFF_EVENT_PATTERNS:
            if re.search(pattern, text):
                event_type = label
                break
        if not event_type:
            return None
        event_date = candidate.candidate_date
        affected_count = self._first_count(candidate.raw_text)
        affected_pct = self._first_percent(candidate.raw_text)
        return EventRecord(
            event_category="layoff",
            event_type=event_type,
            event_date=event_date,
            confidence=self._score(
                event_type_found=True,
                has_date=bool(event_date),
                is_structured=False,
                has_supporting=(candidate.source_field == "news"),
                has_value=(affected_count is not None or affected_pct is not None),
                vague=False,
                contradictory=False,
            ),
            evidence_fields=[candidate.source_field],
            raw_supporting_text=candidate.raw_text[:600],
            extracted_values={
                "affected_count": affected_count,
                "affected_pct": affected_pct,
                "departments": [],
                "locations": [],
            },
            source_strength="news" if candidate.source_field == "news" else "inferred",
            source_url=self._candidate_source_url(candidate),
        )

    def _extract_structured_leadership(self, candidate: NormalizedCandidate) -> list[EventRecord]:
        parsed = candidate.raw_json
        items: list[Any] = parsed if isinstance(parsed, list) else [parsed] if isinstance(parsed, dict) else []
        results: list[EventRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            role = self._clean_text(item.get("role_name") or item.get("title") or item.get("role"))
            label = self._clean_text(item.get("label"))
            person = self._clean_text(item.get("person") or item.get("name"))
            event_date = (
                self._clean_text(item.get("change_date"))
                or self._clean_text(item.get("date"))
                or self._clean_text(item.get("announced_on"))
                or self._clean_text(item.get("key_event_date"))
            )
            blob = f"{role} {label}".lower()
            if not _LEADERSHIP_ROLE_PATTERN.search(blob):
                continue
            change_type = self._clean_text(item.get("change_type")) or self._infer_change_type(label=label, role=role)
            has_verb = bool(_LEADERSHIP_VERB_PATTERN.search(label.lower())) if label else False
            results.append(
                EventRecord(
                    event_category="leadership_change",
                    event_type=change_type or "appointment",
                    event_date=event_date or None,
                    confidence=self._score(
                        event_type_found=True,
                        has_date=bool(event_date),
                        is_structured=True,
                        has_supporting=has_verb or bool(label),
                        has_value=bool(person or role),
                        vague=not has_verb,
                        contradictory=False,
                    ),
                    evidence_fields=[candidate.source_field],
                    raw_supporting_text=(label or candidate.raw_text)[:600],
                    extracted_values={
                        "person_name": person or None,
                        "role": role or None,
                        "previous_company": None,
                    },
                    source_strength="structured",
                    source_url=self._clean_text(item.get("link") or item.get("source_url")) or candidate.source_url,
                )
            )
        return results

    def _extract_text_leadership(self, candidate: NormalizedCandidate) -> EventRecord | None:
        text = candidate.raw_text
        if not _LEADERSHIP_ROLE_PATTERN.search(text.lower()):
            return None
        if not _LEADERSHIP_VERB_PATTERN.search(text.lower()):
            return None
        role_match = _LEADERSHIP_ROLE_PATTERN.search(text.lower())
        role = role_match.group(1) if role_match else ""
        event_date = candidate.candidate_date
        person = self._guess_person_name(text)
        return EventRecord(
            event_category="leadership_change",
            event_type="appointment",
            event_date=event_date,
            confidence=self._score(
                event_type_found=True,
                has_date=bool(event_date),
                is_structured=False,
                has_supporting=(candidate.source_field == "news"),
                has_value=bool(person or role),
                vague=False,
                contradictory=False,
            ),
            evidence_fields=[candidate.source_field],
            raw_supporting_text=text[:600],
            extracted_values={
                "person_name": person,
                "role": role,
                "previous_company": None,
            },
            source_strength="news" if candidate.source_field == "news" else "inferred",
            source_url=self._candidate_source_url(candidate),
        )

    @staticmethod
    def _filter_ranked(events: list[EventRecord], *, min_confidence: float) -> list[EventRecord]:
        kept = [event for event in events if event.confidence >= min_confidence]
        kept.sort(
            key=lambda event: (
                event.event_date or "",
                event.confidence,
            ),
            reverse=True,
        )
        return kept

    @staticmethod
    def _event_hint_for_field(field: str) -> str:
        if field in {"funding_rounds", "funding_rounds_list", "funds_raised", "financials_highlights"}:
            return "funding"
        if field in {"layoff"}:
            return "layoff"
        if field in {"leadership_hire", "current_employees", "people_highlights"}:
            return "leadership"
        return "unknown"

    @classmethod
    def _jsonish(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        text = cls._clean_text(value)
        if not text:
            return None
        if text in {"[]", "{}"}:
            return [] if text == "[]" else {}
        try:
            import json

            return json.loads(text)
        except ValueError:
            return text

    @classmethod
    def _to_text(cls, value: Any, *, raw_json: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(raw_json, (dict, list)):
            return str(raw_json)
        return cls._clean_text(value)

    @classmethod
    def _best_date(cls, value: Any) -> str | None:
        if isinstance(value, str):
            match = _DATE_PATTERN.search(value)
            if not match:
                return None
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        if isinstance(value, dict):
            for key in ("announced_on", "announced_date", "date", "funded_on", "change_date", "key_event_date", "published_at"):
                direct = cls._best_date(value.get(key))
                if direct:
                    return direct
            for nested in value.values():
                direct = cls._best_date(nested)
                if direct:
                    return direct
            return None
        if isinstance(value, list):
            for item in value:
                direct = cls._best_date(item)
                if direct:
                    return direct
        return None

    @staticmethod
    def _score(
        *,
        event_type_found: bool,
        has_date: bool,
        is_structured: bool,
        has_supporting: bool,
        has_value: bool,
        vague: bool,
        contradictory: bool,
    ) -> float:
        score = 0.0
        if event_type_found:
            score += 0.35
        if has_date:
            score += 0.25
        if is_structured:
            score += 0.20
        if has_supporting:
            score += 0.15
        if has_value:
            score += 0.10
        if not has_date:
            score -= 0.30
        if vague:
            score -= 0.25
        if contradictory:
            score -= 0.40
        return round(max(0.0, min(1.0, score)), 2)

    @staticmethod
    def _parse_dt(value: str) -> datetime | None:
        text = (value or "").strip().replace("Z", "+00:00")
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            if _DATE_PATTERN.match(text):
                try:
                    dt = datetime.strptime(text[:10], "%Y-%m-%d")
                except ValueError:
                    return None
            else:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @staticmethod
    def _clean_text(value: Any) -> str:
        text = str(value).strip() if value is not None else ""
        if text.lower() in {"", "null", "none", "nan", "n/a"}:
            return ""
        return text

    @staticmethod
    def _funding_round_name(item: dict[str, Any]) -> str:
        funding_round = item.get("funding_round")
        if isinstance(funding_round, dict):
            funding_round = funding_round.get("value") or funding_round.get("name")
        for key in ("investment_type", "funding_type", "series", "name", "round"):
            value = item.get(key)
            if value:
                return str(value).strip()
        if funding_round:
            return str(funding_round).strip()
        return ""

    @staticmethod
    def _nested_amount_usd(item: dict[str, Any]) -> int | float | None:
        for key in (
            "money_raised",
            "amount",
            "funding_total",
            "raised_amount",
            "funds_raised",
            "funds_total",
            "org_funding_total",
        ):
            value = item.get(key)
            if isinstance(value, dict):
                for nested_key in ("value_usd", "value"):
                    nested = value.get(nested_key)
                    if nested not in (None, ""):
                        try:
                            return float(nested)
                        except (TypeError, ValueError):
                            return None
            elif value not in (None, ""):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _first_usd_amount(text: str) -> int | float | None:
        normalized = text.replace(",", "")
        match = re.search(
            r"(?i)(?:\$\s*|usd\s+)?(\d+(?:\.\d+)?)\s*(m|mm|million|b|bn|billion|k|thousand)\b",
            normalized,
        )
        if not match:
            return None
        try:
            value = float(match.group(1))
            suffix = match.group(2).lower()
            if suffix in {"k", "thousand"}:
                value *= 1_000
            elif suffix in {"m", "mm", "million"}:
                value *= 1_000_000
            elif suffix in {"b", "bn", "billion"}:
                value *= 1_000_000_000
            return value
        except ValueError:
            return None

    @staticmethod
    def _first_count(text: str) -> int | None:
        normalized = text.replace(",", "")
        match = re.search(r"\b(\d{1,6})\b", normalized)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _first_percent(text: str) -> float | None:
        match = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", text)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(str(value).replace(",", "").strip())
        except ValueError:
            return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        text = str(value).replace("%", "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _guess_person_name(text: str) -> str | None:
        match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", text)
        if not match:
            return None
        return match.group(1)

    @staticmethod
    def _infer_change_type(*, label: str, role: str) -> str:
        blob = f"{label} {role}".lower()
        if "promot" in blob:
            return "promotion"
        if "depart" in blob or "resign" in blob or "step down" in blob:
            return "departure"
        if "hire" in blob or "join" in blob:
            return "new_hire"
        return "appointment"

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    @classmethod
    def _candidate_source_url(cls, candidate: NormalizedCandidate) -> str | None:
        parsed = candidate.raw_json
        if isinstance(parsed, dict):
            url = cls._clean_text(parsed.get("url") or parsed.get("link") or parsed.get("source_url"))
            if url:
                return url
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                url = cls._clean_text(item.get("url") or item.get("link") or item.get("source_url"))
                if url:
                    return url
        return candidate.source_url
