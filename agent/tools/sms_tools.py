"""SMS tool wrappers."""

from __future__ import annotations

from agent.services.common.schemas import ProviderSendResult
from agent.services.sms.client import SMSService
from agent.services.sms.schemas import OutboundSMSRequest


async def send_warm_lead_sms(*, service: SMSService, request: OutboundSMSRequest) -> ProviderSendResult:
    return await service.send_warm_lead_sms(request)

