"""Email tool wrappers."""

from __future__ import annotations

from agent.services.common.schemas import ProviderSendResult
from agent.services.email.client import EmailService
from agent.services.email.schemas import OutboundEmailRequest


async def send_email(*, service: EmailService, request: OutboundEmailRequest) -> ProviderSendResult:
    return await service.send_email(request)

