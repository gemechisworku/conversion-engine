"""CRM tool wrappers."""

from __future__ import annotations

from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.crm.schemas import CRMBookingPayload, CRMEnrichmentPayload, CRMLeadPayload, CRMWriteResult


async def crm_upsert_lead(
    *,
    service: HubSpotMCPService,
    lead: CRMLeadPayload,
    trace_id: str,
    idempotency_key: str,
) -> CRMWriteResult:
    return await service.upsert_contact(contact=lead, trace_id=trace_id, idempotency_key=idempotency_key)


async def crm_append_enrichment(
    *,
    service: HubSpotMCPService,
    lead_id: str,
    enrichment: CRMEnrichmentPayload,
    trace_id: str,
    idempotency_key: str,
) -> CRMWriteResult:
    return await service.append_enrichment(
        lead_id=lead_id,
        enrichment=enrichment,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
    )


async def crm_record_booking(
    *,
    service: HubSpotMCPService,
    lead_id: str,
    booking: CRMBookingPayload,
    trace_id: str,
    idempotency_key: str,
) -> CRMWriteResult:
    return await service.record_booking(
        lead_id=lead_id,
        booking=booking,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
    )

