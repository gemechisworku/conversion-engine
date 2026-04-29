"""CRM tool wrappers."""

from __future__ import annotations

from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.crm.schemas import CRMBookingPayload, CRMEnrichmentPayload, CRMLeadPayload, CRMWriteResult
from agent.services.observability.events import log_tool_end, log_tool_error, log_tool_start


async def crm_upsert_lead(
    *,
    service: HubSpotMCPService,
    lead: CRMLeadPayload,
    trace_id: str,
    idempotency_key: str,
) -> CRMWriteResult:
    run_id = log_tool_start(
        trace_id=trace_id,
        tool_name="crm_upsert_lead",
        lead_id=lead.lead_id,
        input_data=lead.model_dump(mode="json"),
    )
    try:
        result = await service.upsert_contact(contact=lead, trace_id=trace_id, idempotency_key=idempotency_key)
        if result.succeeded:
            log_tool_end(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_upsert_lead",
                lead_id=lead.lead_id,
                output_data=result.model_dump(mode="json"),
                status="success",
            )
        else:
            message = result.error.error_message if result.error else "CRM upsert failed."
            retryable = bool(result.error.retryable) if result.error else False
            log_tool_error(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_upsert_lead",
                lead_id=lead.lead_id,
                error={"type": "CRMUpsertFailed", "message": message, "retryable": retryable},
            )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=trace_id,
            run_id=run_id,
            tool_name="crm_upsert_lead",
            lead_id=lead.lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise


async def crm_append_enrichment(
    *,
    service: HubSpotMCPService,
    lead_id: str,
    enrichment: CRMEnrichmentPayload,
    trace_id: str,
    idempotency_key: str,
) -> CRMWriteResult:
    run_id = log_tool_start(
        trace_id=trace_id,
        tool_name="crm_append_enrichment",
        lead_id=lead_id,
        input_data=enrichment.model_dump(mode="json"),
    )
    try:
        result = await service.append_enrichment(
            lead_id=lead_id,
            enrichment=enrichment,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        if result.succeeded:
            log_tool_end(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_append_enrichment",
                lead_id=lead_id,
                output_data=result.model_dump(mode="json"),
                status="success",
            )
        else:
            message = result.error.error_message if result.error else "CRM enrichment write failed."
            retryable = bool(result.error.retryable) if result.error else False
            log_tool_error(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_append_enrichment",
                lead_id=lead_id,
                error={"type": "CRMEnrichmentFailed", "message": message, "retryable": retryable},
            )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=trace_id,
            run_id=run_id,
            tool_name="crm_append_enrichment",
            lead_id=lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise


async def crm_record_booking(
    *,
    service: HubSpotMCPService,
    lead_id: str,
    booking: CRMBookingPayload,
    trace_id: str,
    idempotency_key: str,
) -> CRMWriteResult:
    run_id = log_tool_start(
        trace_id=trace_id,
        tool_name="crm_record_booking",
        lead_id=lead_id,
        input_data=booking.model_dump(mode="json"),
    )
    try:
        result = await service.record_booking(
            lead_id=lead_id,
            booking=booking,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        if result.succeeded:
            log_tool_end(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_record_booking",
                lead_id=lead_id,
                output_data=result.model_dump(mode="json"),
                status="success",
            )
        else:
            message = result.error.error_message if result.error else "CRM booking write failed."
            retryable = bool(result.error.retryable) if result.error else False
            log_tool_error(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_record_booking",
                lead_id=lead_id,
                error={"type": "CRMBookingFailed", "message": message, "retryable": retryable},
            )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=trace_id,
            run_id=run_id,
            tool_name="crm_record_booking",
            lead_id=lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise


async def crm_set_stage(
    *,
    service: HubSpotMCPService,
    lead_id: str,
    stage: str,
    trace_id: str,
    idempotency_key: str,
) -> CRMWriteResult:
    run_id = log_tool_start(
        trace_id=trace_id,
        tool_name="crm_set_stage",
        lead_id=lead_id,
        input_data={"stage": stage},
    )
    try:
        result = await service.set_stage(
            lead_id=lead_id,
            stage=stage,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        if result.succeeded:
            log_tool_end(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_set_stage",
                lead_id=lead_id,
                output_data=result.model_dump(mode="json"),
                status="success",
            )
        else:
            message = result.error.error_message if result.error else "CRM stage write failed."
            retryable = bool(result.error.retryable) if result.error else False
            log_tool_error(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_set_stage",
                lead_id=lead_id,
                error={"type": "CRMStageFailed", "message": message, "retryable": retryable},
            )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=trace_id,
            run_id=run_id,
            tool_name="crm_set_stage",
            lead_id=lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise


async def crm_attach_brief_refs(
    *,
    service: HubSpotMCPService,
    lead_id: str,
    brief_refs: list[str],
    trace_id: str,
    idempotency_key: str,
) -> CRMWriteResult:
    run_id = log_tool_start(
        trace_id=trace_id,
        tool_name="crm_attach_brief_refs",
        lead_id=lead_id,
        input_data={"brief_refs": brief_refs},
    )
    try:
        result = await service.attach_brief_refs(
            lead_id=lead_id,
            brief_refs=brief_refs,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        if result.succeeded:
            log_tool_end(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_attach_brief_refs",
                lead_id=lead_id,
                output_data=result.model_dump(mode="json"),
                status="success",
            )
        else:
            message = result.error.error_message if result.error else "CRM brief-refs write failed."
            retryable = bool(result.error.retryable) if result.error else False
            log_tool_error(
                trace_id=trace_id,
                run_id=run_id,
                tool_name="crm_attach_brief_refs",
                lead_id=lead_id,
                error={"type": "CRMBriefRefsFailed", "message": message, "retryable": retryable},
            )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=trace_id,
            run_id=run_id,
            tool_name="crm_attach_brief_refs",
            lead_id=lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise
