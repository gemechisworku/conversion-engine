"""Crunchbase enrichment adapter."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from agent.config.settings import Settings
from agent.services.enrichment.schemas import EnrichmentBrief, Firmographics, SignalSnapshot, SourceRef

DEFAULT_CRUNCHBASE_DATASET_PATH = "tenacious_sales_data/crunchbase-companies-information.csv"


class CrunchbaseAdapter:
    # Implements: FR-1, FR-2
    # Workflow: lead_intake_and_enrichment.md
    # Schema: evidence_record.md
    # API: research_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def collect(self, *, company_id: str, company_domain: str | None = None) -> SignalSnapshot:
        record = await self._load_record(company_id=company_id, company_domain=company_domain)
        if not record:
            return SignalSnapshot(
                summary={"company_id": company_id, "found": False},
                confidence=0.25,
                source_refs=[
                    SourceRef(source_name="crunchbase", source_url=self._settings.crunchbase_dataset_url or None)
                ],
            )
        record_id = str(record.get("company_id") or record.get("id") or "").strip()
        confidence = 0.95 if record_id == company_id else 0.8
        return SignalSnapshot(
            summary={
                "company_id": record.get("company_id") or company_id,
                "company_name": self._company_name(record),
                "domain": self._domain(record),
                "industry": self._industry(record),
                "industries": self._industry_values(record),
                "funding_round": record.get("funding_round"),
                "funding_amount_usd": record.get("funding_amount_usd"),
                "funding_date": record.get("funding_date"),
                "funding_events_180d": self._funding_events(row=record, lookback_days=180),
                "location": record.get("location") or record.get("address"),
                "employee_count": record.get("num_employees"),
                "tech_stack": self._tech_stack(row=record),
                "social_media_links": self._jsonish(record.get("social_media_links")),
                "people_highlights": self._jsonish(record.get("people_highlights")),
                "overview_highlights": self._jsonish(record.get("overview_highlights")),
                "full_description": record.get("full_description"),
                "num_news": record.get("num_news"),
                "monthly_visits": record.get("monthly_visits"),
                "leadership_hire": self._jsonish(record.get("leadership_hire")),
                "layoff": self._jsonish(record.get("layoff")),
                "news": self._jsonish(record.get("news")),
            },
            confidence=confidence,
            source_refs=[
                SourceRef(
                    source_name="crunchbase",
                    source_url=str(record.get("source_url") or self._settings.crunchbase_dataset_url or ""),
                )
            ],
        )

    async def build_enrichment_brief(
        self,
        *,
        lead_id: str,
        company_id: str | None = None,
        company_name: str | None = None,
        company_domain: str | None = None,
        inbound_email: str | None = None,
        inbound_phone: str | None = None,
    ) -> EnrichmentBrief:
        record = await self.resolve_record(
            company_id=company_id,
            company_name=company_name,
            company_domain=company_domain,
            inbound_email=inbound_email,
            inbound_phone=inbound_phone,
        )
        if record is None:
            return EnrichmentBrief(
                brief_id=f"enrich_{lead_id}",
                lead_id=lead_id,
                company_id=company_id,
                matched=False,
                match_type="none",
                matched_identifier=None,
                match_confidence=0.0,
                firmographics=Firmographics(),
                source_refs=[SourceRef(source_name="crunchbase_odm", source_url=str(self._dataset_ref()))],
                risk_notes=["No local Crunchbase ODM match found for inbound identity."],
            )

        match_type = str(record.get("_match_type") or "unknown")
        matched_identifier = str(record.get("_matched_identifier") or "").strip() or None
        confidence = float(record.get("_match_confidence") or 0.5)
        return EnrichmentBrief(
            brief_id=f"enrich_{lead_id}",
            lead_id=lead_id,
            company_id=str(record.get("id") or record.get("company_id") or company_id or ""),
            matched=True,
            match_type=match_type,
            matched_identifier=matched_identifier,
            match_confidence=confidence,
            firmographics=self._firmographics(record),
            source_refs=[
                SourceRef(
                    source_name="crunchbase_odm_local",
                    source_url=str(record.get("url") or self._dataset_ref() or ""),
                )
            ],
            risk_notes=[] if confidence >= 0.8 else ["Match is not exact; soften company-specific claims."],
        )

    async def resolve_record(
        self,
        *,
        company_id: str | None = None,
        company_name: str | None = None,
        company_domain: str | None = None,
        inbound_email: str | None = None,
        inbound_phone: str | None = None,
    ) -> dict[str, Any] | None:
        rows = await self._load_rows()
        if not rows:
            return None
        email_domain = self._domain_from_email(inbound_email)
        candidates = [
            ("company_id", company_id, 0.98),
            ("domain", company_domain, 0.9),
            ("email_domain", email_domain, 0.86),
            ("phone", inbound_phone, 0.72),
            ("company_name", company_name, 0.7),
        ]
        for match_type, value, confidence in candidates:
            if not value:
                continue
            for row in rows:
                if self._row_matches(row=row, match_type=match_type, value=str(value)):
                    matched = dict(row)
                    matched["_match_type"] = match_type
                    matched["_matched_identifier"] = str(value)
                    matched["_match_confidence"] = confidence
                    return matched
        return None

    async def _load_record(self, *, company_id: str, company_domain: str | None) -> dict[str, Any] | None:
        path = self._dataset_path()
        if path is not None and path.exists():
            return self._load_from_file(path=path, company_id=company_id, company_domain=company_domain)
        if self._settings.crunchbase_dataset_url:
            return await self._load_from_url(
                url=self._settings.crunchbase_dataset_url,
                company_id=company_id,
                company_domain=company_domain,
            )
        return None

    async def _load_rows(self) -> list[dict[str, Any]]:
        path = self._dataset_path()
        if path is not None and path.exists():
            return self._rows_from_file(path=path)
        if self._settings.crunchbase_dataset_url:
            response = await self._get(url=self._settings.crunchbase_dataset_url)
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

    async def load_rows(self) -> list[dict[str, Any]]:
        """Return allowed local/URL Crunchbase rows for downstream read-only analysis."""
        return await self._load_rows()

    def _dataset_path(self) -> Path | None:
        configured = self._settings.crunchbase_dataset_path.strip()
        if configured:
            return Path(configured)
        default = Path(DEFAULT_CRUNCHBASE_DATASET_PATH)
        if default.exists():
            return default
        return None

    def _dataset_ref(self) -> str | None:
        path = self._dataset_path()
        if path is not None:
            return str(path)
        return self._settings.crunchbase_dataset_url or None

    def _load_from_file(
        self,
        *,
        path: Path,
        company_id: str,
        company_domain: str | None,
    ) -> dict[str, Any] | None:
        if path.suffix.lower() == ".json":
            rows = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                return None
            return self._match_record(rows=rows, company_id=company_id, company_domain=company_domain)
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return self._match_record(rows=list(reader), company_id=company_id, company_domain=company_domain)

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

    async def _load_from_url(
        self,
        *,
        url: str,
        company_id: str,
        company_domain: str | None,
    ) -> dict[str, Any] | None:
        response = await self._get(url=url)
        if not response.is_success:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        rows: list[dict[str, Any]]
        if isinstance(payload, dict):
            rows = [payload]
        elif isinstance(payload, list):
            rows = [row for row in payload if isinstance(row, dict)]
        else:
            return None
        return self._match_record(rows=rows, company_id=company_id, company_domain=company_domain)

    @staticmethod
    def _match_record(
        *,
        rows: list[dict[str, Any]],
        company_id: str,
        company_domain: str | None,
    ) -> dict[str, Any] | None:
        for row in rows:
            row_company_id = str(row.get("company_id") or row.get("id") or "").strip()
            row_domain = CrunchbaseAdapter._domain(row)
            if row_company_id and row_company_id == company_id:
                return row
            if company_domain and row_domain and row_domain == company_domain.lower():
                return row
        return None

    @staticmethod
    def _row_matches(*, row: dict[str, Any], match_type: str, value: str) -> bool:
        normalized = value.strip().lower()
        if not normalized:
            return False
        if match_type == "company_id":
            return normalized in {
                str(row.get("company_id") or "").strip().lower(),
                str(row.get("id") or "").strip().lower(),
                str(row.get("uuid") or "").strip().lower(),
            }
        if match_type in {"domain", "email_domain"}:
            return normalized == CrunchbaseAdapter._domain(row)
        if match_type == "phone":
            return CrunchbaseAdapter._digits(normalized) == CrunchbaseAdapter._digits(str(row.get("contact_phone") or ""))
        if match_type == "company_name":
            return normalized == CrunchbaseAdapter._company_name(row).lower()
        return False

    @staticmethod
    def _firmographics(row: dict[str, Any]) -> Firmographics:
        industries = CrunchbaseAdapter._industry_values(row)
        return Firmographics(
            company_name=CrunchbaseAdapter._company_name(row) or None,
            domain=CrunchbaseAdapter._domain(row) or None,
            website=str(row.get("website") or "").strip() or None,
            industry=industries[0] if industries else CrunchbaseAdapter._industry(row) or None,
            industries=industries,
            location=str(row.get("address") or row.get("location") or "").strip() or None,
            region=str(row.get("region") or "").strip() or None,
            employee_count=str(row.get("num_employees") or "").strip() or None,
            founded_date=str(row.get("founded_date") or "").strip() or None,
            funding_rounds=str(row.get("funding_rounds") or row.get("funding_rounds_list") or "").strip() or None,
            funding_total=str(row.get("funds_total") or row.get("funds_raised") or "").strip() or None,
            operating_status=str(row.get("operating_status") or "").strip() or None,
            crunchbase_url=str(row.get("url") or "").strip() or None,
        )

    @staticmethod
    def _company_name(row: dict[str, Any]) -> str:
        return str(row.get("company_name") or row.get("name") or "").strip()

    @staticmethod
    def _domain(row: dict[str, Any]) -> str:
        raw = str(row.get("domain") or row.get("website") or "").strip().lower()
        if not raw:
            return ""
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = parsed.netloc or parsed.path
        return host.removeprefix("www.").split("/")[0]

    @staticmethod
    def _domain_from_email(value: str | None) -> str:
        if not value or "@" not in value:
            return ""
        return value.rsplit("@", 1)[1].strip().lower().removeprefix("www.")

    @staticmethod
    def _industry(row: dict[str, Any]) -> str:
        values = CrunchbaseAdapter._industry_values(row)
        return values[0] if values else str(row.get("industry") or "").strip()

    @staticmethod
    def _industry_values(row: dict[str, Any]) -> list[str]:
        raw = row.get("industries") or row.get("industry") or ""
        if isinstance(raw, list):
            return [str(item.get("value") if isinstance(item, dict) else item).strip() for item in raw if item]
        text = str(raw).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except ValueError:
            return [text]
        if isinstance(parsed, list):
            values: list[str] = []
            for item in parsed:
                if isinstance(item, dict):
                    value = str(item.get("value") or item.get("id") or "").strip()
                else:
                    value = str(item).strip()
                if value:
                    values.append(value)
            return values
        return [text]

    @staticmethod
    def _jsonish(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        text = str(value).strip()
        if not text or text.lower() in {"null", "none", "{}"}:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text

    @classmethod
    def _funding_events(cls, *, row: dict[str, Any], lookback_days: int) -> list[dict[str, Any]]:
        parsed = cls._jsonish(row.get("funding_rounds_list") or row.get("funding_rounds"))
        rows: list[Any]
        if isinstance(parsed, list):
            rows = parsed
        elif isinstance(parsed, dict):
            rows = parsed.get("items") if isinstance(parsed.get("items"), list) else [parsed]
        else:
            rows = []
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        events: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            date_text = str(
                item.get("announced_on")
                or item.get("announced_date")
                or item.get("date")
                or item.get("funded_on")
                or ""
            ).strip()
            event_date = cls._parse_dt(date_text)
            if event_date is None or event_date < cutoff:
                continue
            events.append(
                {
                    "round": item.get("investment_type")
                    or item.get("funding_type")
                    or item.get("series")
                    or item.get("name")
                    or item.get("round")
                    or "funding_event",
                    "announced_on": event_date.date().isoformat(),
                    "amount_usd": cls._nested_amount_usd(item),
                    "evidence_ref": "crunchbase_signal",
                }
            )
        return events

    @staticmethod
    def _nested_amount_usd(item: dict[str, Any]) -> Any:
        for key in ("money_raised", "amount", "funding_total", "raised_amount"):
            value = item.get(key)
            if isinstance(value, dict):
                return value.get("value_usd") or value.get("value")
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _parse_dt(value: str) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = datetime.strptime(value[:10], "%Y-%m-%d")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @classmethod
    def _tech_stack(cls, *, row: dict[str, Any]) -> list[str]:
        parsed = cls._jsonish(row.get("builtwith_tech") or row.get("siftery_products") or row.get("technology_highlights"))
        values: list[str] = []
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("value") or "").strip()
                else:
                    name = str(item).strip()
                if name and name not in values:
                    values.append(name)
        elif isinstance(parsed, dict):
            for key, value in parsed.items():
                if value and str(key) not in values:
                    values.append(str(key))
        return values[:25]

    @staticmethod
    def _digits(value: str) -> str:
        return "".join(char for char in value if char.isdigit())

    async def _get(self, *, url: str) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.get(url)
