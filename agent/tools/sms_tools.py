"""SMS tool wrappers."""

from __future__ import annotations

from agent.services.common.schemas import ProviderSendResult
from agent.services.observability.events import log_tool_end, log_tool_error, log_tool_start
from agent.services.sms.client import SMSService
from agent.services.sms.schemas import OutboundSMSRequest


async def send_warm_lead_sms(*, service: SMSService, request: OutboundSMSRequest) -> ProviderSendResult:
    run_id = log_tool_start(
        trace_id=request.trace_id,
        tool_name="send_warm_lead_sms",
        lead_id=request.lead_id,
        input_data=request.model_dump(mode="json"),
    )
    try:
        result = await service.send_warm_lead_sms(request)
        if result.accepted:
            log_tool_end(
                trace_id=request.trace_id,
                run_id=run_id,
                tool_name="send_warm_lead_sms",
                lead_id=request.lead_id,
                output_data=result.model_dump(mode="json"),
                status="success",
            )
        else:
            err = result.error.model_dump(mode="json") if result.error else {
                "type": "DeliveryError",
                "message": "SMS send failed.",
                "retryable": False,
            }
            log_tool_error(
                trace_id=request.trace_id,
                run_id=run_id,
                tool_name="send_warm_lead_sms",
                lead_id=request.lead_id,
                error={
                    "type": err.get("error_code", "DeliveryError"),
                    "message": err.get("error_message", "SMS send failed."),
                    "retryable": bool(err.get("retryable", False)),
                },
            )
        return result
    except Exception as exc:
        log_tool_error(
            trace_id=request.trace_id,
            run_id=run_id,
            tool_name="send_warm_lead_sms",
            lead_id=request.lead_id,
            error={"type": type(exc).__name__, "message": str(exc), "retryable": True},
        )
        raise
