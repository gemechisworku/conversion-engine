"""Inbound SMS routing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from agent.services.sms.schemas import InboundSMSEvent

SMSEventHandler = Callable[[InboundSMSEvent], Awaitable[None]]


class SMSRouter:
    # Implements: FR-9, FR-10
    # Workflow: reply_handling.md
    # Schema: conversation_state.md
    # API: orchestration_api.md
    def __init__(
        self,
        *,
        on_inbound_sms: SMSEventHandler | None = None,
        on_delivery_report: SMSEventHandler | None = None,
        on_unknown: SMSEventHandler | None = None,
        on_malformed: SMSEventHandler | None = None,
    ) -> None:
        self._on_inbound_sms = on_inbound_sms or self._noop
        self._on_delivery_report = on_delivery_report or self._noop
        self._on_unknown = on_unknown or self._noop
        self._on_malformed = on_malformed or self._noop

    async def route(self, event: InboundSMSEvent) -> None:
        if event.event_type == "inbound_sms":
            await self._on_inbound_sms(event)
            return
        if event.event_type == "delivery_report":
            await self._on_delivery_report(event)
            return
        if event.event_type == "malformed":
            await self._on_malformed(event)
            return
        await self._on_unknown(event)

    @staticmethod
    async def _noop(_: InboundSMSEvent) -> None:
        return

