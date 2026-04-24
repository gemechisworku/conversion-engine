"""CRM sync node — HubSpot upsert + enrichment payload (Phase 5)."""

from __future__ import annotations

from typing import Any

from agent.graphs.state import LeadGraphState
from agent.services.crm.hubspot_mcp import HubSpotMCPService, map_enrichment_to_crm_payload
from agent.services.crm.schemas import CRMLeadPayload
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.services.observability.events import log_processing_step


async def crm_sync_lead_intake_node(*, state: dict[str, Any], hubspot: HubSpotMCPService | None) -> dict[str, Any]:
    if hubspot is None:
        log_processing_step(
            component="nodes.crm_sync",
            step="crm_sync.skip",
            message="HubSpot not configured; skipping CRM sync node",
            lead_id=state.get("lead_id"),
            trace_id=state.get("trace_id"),
        )
        return {"crm_synced": False}
    log_processing_step(
        component="nodes.crm_sync",
        step="crm_sync.start",
        message="Syncing lead to HubSpot",
        lead_id=state.get("lead_id"),
        trace_id=state.get("trace_id"),
    )
    enriched = LeadGraphState.model_validate(state["enriched_state"])
    artifact = EnrichmentArtifact.model_validate(state["artifact"])
    lead_id = state["lead_id"]
    await hubspot.upsert_contact(
        contact=CRMLeadPayload(
            lead_id=lead_id,
            company_id=state["company_id"],
            company_name=state["company_name"],
            company_domain=state.get("company_domain") or None,
        ),
        trace_id=state["trace_id"],
        idempotency_key=state["idempotency_key"],
    )
    await hubspot.append_enrichment(
        lead_id=lead_id,
        enrichment=map_enrichment_to_crm_payload(
            lead_id=lead_id,
            enrichment_artifact=artifact.model_dump(mode="json"),
        ),
        trace_id=state["trace_id"],
        idempotency_key=f"{state['idempotency_key']}:enrichment",
    )
    await hubspot.set_stage(
        lead_id=lead_id,
        stage="brief_ready",
        trace_id=state["trace_id"],
        idempotency_key=f"{state['idempotency_key']}:stage",
    )
    await hubspot.attach_brief_refs(
        lead_id=lead_id,
        brief_refs=enriched.brief_refs,
        trace_id=state["trace_id"],
        idempotency_key=f"{state['idempotency_key']}:brief_refs",
    )
    log_processing_step(
        component="nodes.crm_sync",
        step="crm_sync.done",
        message="HubSpot CRM sync completed",
        lead_id=lead_id,
        trace_id=state.get("trace_id"),
    )
    return {"crm_synced": True}
