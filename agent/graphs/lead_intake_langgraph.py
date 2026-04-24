"""LangGraph orchestration: enrichment then optional HubSpot CRM sync."""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from agent.graphs.lead_graph import run_lead_intake
from agent.graphs.state import LeadGraphState
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.crm.hubspot_mcp import HubSpotMCPService, map_enrichment_to_crm_payload
from agent.services.crm.schemas import CRMLeadPayload
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.services.observability.events import log_processing_step


class LeadIntakeGraphState(TypedDict, total=False):
    # Implements: FR-14
    # Workflow: lead_intake_and_enrichment.md
    # Schema: session_state.md
    # API: orchestration_api.md
    lead_id: str
    company_id: str
    company_name: str
    company_domain: str
    trace_id: str
    idempotency_key: str
    lead_state: dict[str, Any]
    enriched_state: dict[str, Any]
    artifact: dict[str, Any]
    crm_synced: bool
    errors: Annotated[list[str], operator.add]


@dataclass
class LeadIntakeGraphDeps:
    hubspot: HubSpotMCPService | None
    enrichment_services: dict[str, Any]
    state_repo: SQLiteStateRepository

    def services_for_enrich(self) -> dict[str, Any]:
        return {**self.enrichment_services, "state_repo": self.state_repo}


def compile_lead_intake_graph(deps: LeadIntakeGraphDeps):
    graph: StateGraph = StateGraph(LeadIntakeGraphState)

    async def enrich_node(state: LeadIntakeGraphState) -> dict[str, Any]:
        lead_state = LeadGraphState.model_validate(state["lead_state"])
        log_processing_step(
            component="graphs.lead_intake",
            step="enrich.start",
            message="Running lead enrichment (signals + briefs)",
            lead_id=state.get("lead_id"),
            trace_id=state.get("trace_id"),
            company_id=state.get("company_id"),
            company_name=state.get("company_name"),
            company_domain=state.get("company_domain"),
        )
        enrich_services = deps.services_for_enrich()
        enrich_services["trace_id"] = state.get("trace_id", "")
        enrich_services["lead_id"] = state.get("lead_id", "")
        enriched, artifact = await run_lead_intake(
            state=lead_state,
            company_name=state["company_name"],
            company_domain=state["company_domain"],
            services=enrich_services,
        )
        log_processing_step(
            component="graphs.lead_intake",
            step="enrich.done",
            message="Lead enrichment finished",
            lead_id=state.get("lead_id"),
            trace_id=state.get("trace_id"),
            stage=enriched.current_stage,
            brief_refs_count=len(enriched.brief_refs),
            company_id=enriched.company_id,
        )
        return {
            "enriched_state": enriched.model_dump(mode="json"),
            "artifact": artifact.model_dump(mode="json"),
        }

    async def crm_sync_node(state: LeadIntakeGraphState) -> dict[str, Any]:
        if deps.hubspot is None:
            log_processing_step(
                component="graphs.lead_intake",
                step="crm_sync.skip",
                message="HubSpot not configured; skipping CRM sync node",
                lead_id=state.get("lead_id"),
                trace_id=state.get("trace_id"),
            )
            return {"crm_synced": False}
        log_processing_step(
            component="graphs.lead_intake",
            step="crm_sync.start",
            message="Syncing lead to HubSpot (upsert, enrichment payload, stage, brief refs)",
            lead_id=state.get("lead_id"),
            trace_id=state.get("trace_id"),
            idempotency_key=state.get("idempotency_key"),
        )
        enriched = LeadGraphState.model_validate(state["enriched_state"])
        artifact = EnrichmentArtifact.model_validate(state["artifact"])
        lead_id = state["lead_id"]
        await deps.hubspot.upsert_contact(
            contact=CRMLeadPayload(
                lead_id=lead_id,
                company_id=state["company_id"],
                company_name=state["company_name"],
                company_domain=state["company_domain"] or None,
            ),
            trace_id=state["trace_id"],
            idempotency_key=state["idempotency_key"],
        )
        await deps.hubspot.append_enrichment(
            lead_id=lead_id,
            enrichment=map_enrichment_to_crm_payload(
                lead_id=lead_id,
                enrichment_artifact=artifact.model_dump(mode="json"),
            ),
            trace_id=state["trace_id"],
            idempotency_key=f"{state['idempotency_key']}:enrichment",
        )
        await deps.hubspot.set_stage(
            lead_id=lead_id,
            stage="brief_ready",
            trace_id=state["trace_id"],
            idempotency_key=f"{state['idempotency_key']}:stage",
        )
        await deps.hubspot.attach_brief_refs(
            lead_id=lead_id,
            brief_refs=enriched.brief_refs,
            trace_id=state["trace_id"],
            idempotency_key=f"{state['idempotency_key']}:brief_refs",
        )
        log_processing_step(
            component="graphs.lead_intake",
            step="crm_sync.done",
            message="HubSpot CRM sync completed",
            lead_id=lead_id,
            trace_id=state.get("trace_id"),
            brief_refs_count=len(enriched.brief_refs),
        )
        return {"crm_synced": True}

    graph.add_node("enrich", enrich_node)
    graph.add_node("crm_sync", crm_sync_node)
    graph.set_entry_point("enrich")
    graph.add_edge("enrich", "crm_sync")
    graph.add_edge("crm_sync", END)
    return graph.compile()
