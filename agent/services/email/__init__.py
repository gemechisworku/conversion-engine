"""Email channel services."""

from .client import EmailService, ResendEmailClient
from .router import EmailEventRouter
from .schemas import InboundEmailEvent, OutboundEmailRequest
from .webhook import ResendWebhookParser

__all__ = [
    "EmailService",
    "ResendEmailClient",
    "EmailEventRouter",
    "InboundEmailEvent",
    "OutboundEmailRequest",
    "ResendWebhookParser",
]

