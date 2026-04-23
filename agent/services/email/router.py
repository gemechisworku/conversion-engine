"""Inbound email event routing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from agent.services.email.schemas import InboundEmailEvent

EventHandler = Callable[[InboundEmailEvent], Awaitable[None]]


class EmailEventRouter:
    # Implements: FR-9, FR-10
    # Workflow: reply_handling.md
    # Schema: conversation_state.md
    # API: orchestration_api.md
    def __init__(
        self,
        *,
        on_reply: EventHandler | None = None,
        on_bounce: EventHandler | None = None,
        on_delivery_failure: EventHandler | None = None,
        on_unknown: EventHandler | None = None,
        on_malformed: EventHandler | None = None,
    ) -> None:
        self._on_reply = on_reply or self._noop
        self._on_bounce = on_bounce or self._noop
        self._on_delivery_failure = on_delivery_failure or self._noop
        self._on_unknown = on_unknown or self._noop
        self._on_malformed = on_malformed or self._noop

    async def route_inbound_reply(self, event: InboundEmailEvent) -> None:
        await self._on_reply(event)

    async def route_bounce(self, event: InboundEmailEvent) -> None:
        await self._on_bounce(event)

    async def route_delivery_failure(self, event: InboundEmailEvent) -> None:
        await self._on_delivery_failure(event)

    async def route_unknown(self, event: InboundEmailEvent) -> None:
        await self._on_unknown(event)

    async def route_malformed(self, event: InboundEmailEvent) -> None:
        await self._on_malformed(event)

    async def route(self, event: InboundEmailEvent) -> None:
        if event.event_type == "reply":
            await self.route_inbound_reply(event)
            return
        if event.event_type == "bounce":
            await self.route_bounce(event)
            return
        if event.event_type == "delivery_failure":
            await self.route_delivery_failure(event)
            return
        if event.event_type == "malformed":
            await self.route_malformed(event)
            return
        await self.route_unknown(event)

    @staticmethod
    async def _noop(_: InboundEmailEvent) -> None:
        return

