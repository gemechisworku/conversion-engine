"""Act II pre-reply enrichment pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from agent.config.settings import Settings
from agent.services.enrichment.cfpb import CFPBComplaintAdapter
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.news_playwright import PublicNewsPlaywrightRetriever
from agent.services.enrichment.schemas import ActIIEnrichmentContext


class ActIIEnrichmentPipeline:
    # Implements: FR-2, FR-9, FR-15
    # Workflow: reply_handling.md
    # Schema: conversation_state.md
    # API: orchestration_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        crunchbase: CrunchbaseAdapter,
        cfpb: CFPBComplaintAdapter,
        news: PublicNewsPlaywrightRetriever,
    ) -> None:
        self._settings = settings
        self._crunchbase = crunchbase
        self._cfpb = cfpb
        self._news = news

    async def run_before_reply(
        self,
        *,
        lead_id: str,
        company_id: str | None,
        company_name: str | None = None,
        company_domain: str | None = None,
        from_email: str | None = None,
        from_number: str | None = None,
    ) -> ActIIEnrichmentContext:
        enrichment_brief = await self._crunchbase.build_enrichment_brief(
            lead_id=lead_id,
            company_id=company_id,
            company_name=company_name,
            company_domain=company_domain,
            inbound_email=from_email,
            inbound_phone=from_number,
        )
        compliance_brief = await self._cfpb.build_compliance_brief(
            lead_id=lead_id,
            enrichment_brief=enrichment_brief,
        )
        news_brief = await self._news.build_news_brief(
            lead_id=lead_id,
            enrichment_brief=enrichment_brief,
        )
        context = ActIIEnrichmentContext(
            lead_id=lead_id,
            enrichment_brief=enrichment_brief,
            compliance_brief=compliance_brief,
            news_brief=news_brief,
        )
        paths = self._write_artifacts(context=context)
        return context.model_copy(update={"artifact_paths": paths})

    def _write_artifacts(self, *, context: ActIIEnrichmentContext) -> dict[str, str]:
        lead_dir = Path(self._settings.act2_evidence_dir) / context.lead_id
        lead_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "enrichment_brief": context.enrichment_brief.model_dump(mode="json"),
            "compliance_brief": context.compliance_brief.model_dump(mode="json"),
            "news_brief": context.news_brief.model_dump(mode="json"),
        }
        paths: dict[str, str] = {}
        for name, payload in artifacts.items():
            path = lead_dir / f"{name}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            paths[name] = str(path)
        return paths
