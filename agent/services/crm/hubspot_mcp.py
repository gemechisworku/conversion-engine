"""HubSpot remote MCP client wrapper."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from agent.config.settings import Settings
from agent.services.common.schemas import ErrorEnvelope
from agent.services.crm.schemas import CRMBookingPayload, CRMEnrichmentPayload, CRMLeadPayload, CRMWriteResult
from agent.services.observability.events import log_trace_event
from agent.services.policy.outbound_policy import OutboundPolicyService


class _MCPCallError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.details = details or {}


class HubSpotMCPService:
    # Implements: FR-12
    # Workflow: crm_sync.md
    # Schema: crm_event.md
    # API: crm_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        policy_service: OutboundPolicyService,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int = 2,
    ) -> None:
        self._settings = settings
        self._policy_service = policy_service
        self._http_client = http_client
        self._max_retries = max_retries

        self._server_url = self._validated_server_url(self._settings.hubspot_mcp_server_url)
        self._oauth_token_url = self._validated_server_url(self._settings.hubspot_mcp_oauth_token_url)
        self._protocol_version = self._settings.hubspot_mcp_protocol_version.strip() or "2025-06-18"

        self._access_token = self._settings.hubspot_mcp_access_token.strip()
        self._refresh_token = self._settings.hubspot_mcp_refresh_token.strip()
        self._client_id = self._settings.hubspot_mcp_client_id.strip()
        self._client_secret = self._settings.hubspot_mcp_client_secret.strip()

        self._session_id: str | None = None
        self._initialized = False
        self._request_counter = 0
        self._init_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._tools_cache: list[dict[str, Any]] | None = None

    async def upsert_contact(
        self,
        *,
        contact: CRMLeadPayload,
        trace_id: str,
        idempotency_key: str,
    ) -> CRMWriteResult:
        payload = {"lead": contact.model_dump(mode="json"), "event_key": idempotency_key}
        return await self._write(
            operation="upsert_lead",
            payload=payload,
            trace_id=trace_id,
            lead_id=contact.lead_id,
            idempotency_key=idempotency_key,
            success_status="upserted",
        )

    async def append_enrichment(
        self,
        *,
        lead_id: str,
        enrichment: CRMEnrichmentPayload,
        trace_id: str,
        idempotency_key: str,
    ) -> CRMWriteResult:
        payload = {
            "lead_id": lead_id,
            "event_type": "enrichment_updated",
            "event_key": idempotency_key,
            "payload": enrichment.model_dump(mode="json"),
        }
        return await self._write(
            operation="append_event",
            payload=payload,
            trace_id=trace_id,
            lead_id=lead_id,
            idempotency_key=idempotency_key,
            success_status="event_recorded",
        )

    async def record_booking(
        self,
        *,
        lead_id: str,
        booking: CRMBookingPayload,
        trace_id: str,
        idempotency_key: str,
    ) -> CRMWriteResult:
        payload = {
            "lead_id": lead_id,
            "event_type": "booking_confirmed",
            "event_key": idempotency_key,
            "payload": booking.model_dump(mode="json"),
        }
        return await self._write(
            operation="append_event",
            payload=payload,
            trace_id=trace_id,
            lead_id=lead_id,
            idempotency_key=idempotency_key,
            success_status="event_recorded",
        )

    async def list_tools(self) -> list[str]:
        tools = await self._list_tools()
        names: list[str] = []
        for tool in tools:
            name = tool.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name)
        return sorted(set(names))

    async def _write(
        self,
        *,
        operation: str,
        payload: dict[str, Any],
        trace_id: str,
        lead_id: str,
        idempotency_key: str,
        success_status: str,
    ) -> CRMWriteResult:
        decisions = self._policy_service.check_email_send(trace_id=trace_id, lead_id=lead_id)
        blocked = next((decision for decision in decisions if not decision.is_allowed), None)
        if blocked:
            error = ErrorEnvelope(
                error_code="POLICY_BLOCKED",
                error_message=blocked.reason,
                retryable=False,
                details={"policy_type": blocked.policy_type},
            )
            return CRMWriteResult(status="blocked", lead_id=lead_id, error=error)

        attempt = 0
        while True:
            attempt += 1
            try:
                tool_name = await self._resolve_tool_name(operation=operation)
                if not tool_name:
                    return CRMWriteResult(
                        status="failed",
                        lead_id=lead_id,
                        error=ErrorEnvelope(
                            error_code="CONFIG_ERROR",
                            error_message=(
                                "No HubSpot MCP tool mapping found. Set "
                                "HUBSPOT_MCP_TOOL_UPSERT_LEAD / HUBSPOT_MCP_TOOL_APPEND_EVENT "
                                "or run the hubspot-tools smoke command to inspect available tools."
                            ),
                            retryable=False,
                        ),
                    )

                tool_arguments = await self._prepare_tool_arguments(
                    tool_name=tool_name,
                    operation=operation,
                    payload=payload,
                )
                projection_summary: dict[str, Any] | None = None
                if operation == "append_event":
                    projection_summary = await self._apply_best_effort_event_projection(
                        tool_name=tool_name,
                        payload=payload,
                        trace_id=trace_id,
                        lead_id=lead_id,
                    )
                raw_tool_result = await self._call_tool(name=tool_name, arguments=tool_arguments)
                tool_error = self._tool_error_message(raw_tool_result)
                if tool_error:
                    raise _MCPCallError(
                        f"HubSpot MCP tool '{tool_name}' failed: {tool_error}",
                        retryable=False,
                        details={"tool_name": tool_name, "tool_result": raw_tool_result},
                    )
                record_id, event_id = self._extract_ids(raw_tool_result)
                raw = {"tool_name": tool_name, "tool_result": raw_tool_result}
                if projection_summary is not None:
                    raw["projection"] = projection_summary
                result = CRMWriteResult(
                    status=success_status,
                    lead_id=lead_id,
                    record_id=record_id,
                    event_id=event_id,
                    raw_response=raw,
                )
                log_trace_event(
                    event_type="crm_write_succeeded",
                    trace_id=trace_id,
                    lead_id=lead_id,
                    status="success",
                    payload={"operation": operation, "tool_name": tool_name, "idempotency_key": idempotency_key},
                )
                return result
            except ValueError as exc:
                return CRMWriteResult(
                    status="failed",
                    lead_id=lead_id,
                    error=ErrorEnvelope(
                        error_code="CONFIG_ERROR",
                        error_message=str(exc),
                        retryable=False,
                    ),
                )
            except _MCPCallError as exc:
                if exc.retryable and attempt <= self._max_retries:
                    continue
                return CRMWriteResult(
                    status="failed",
                    lead_id=lead_id,
                    error=ErrorEnvelope(
                        error_code="CRM_SYNC_FAILED",
                        error_message=str(exc),
                        retryable=exc.retryable,
                        details={"attempt": attempt, **exc.details},
                    ),
                )
            except httpx.TimeoutException as exc:
                if attempt <= self._max_retries:
                    continue
                return CRMWriteResult(
                    status="failed",
                    lead_id=lead_id,
                    error=ErrorEnvelope(error_code="TOOL_TIMEOUT", error_message=str(exc), retryable=True),
                )
            except httpx.HTTPError as exc:
                if attempt <= self._max_retries:
                    continue
                return CRMWriteResult(
                    status="failed",
                    lead_id=lead_id,
                    error=ErrorEnvelope(error_code="SOURCE_UNAVAILABLE", error_message=str(exc), retryable=True),
                )

    async def _apply_best_effort_event_projection(
        self,
        *,
        tool_name: str,
        payload: dict[str, Any],
        trace_id: str,
        lead_id: str,
    ) -> dict[str, Any]:
        """Project high-value CRM events into company properties.

        This is best-effort and should not block the canonical event write.
        """
        if tool_name != "manage_crm_objects":
            return {"applied": False, "reason": "unsupported_tool"}
        args = await self._build_manage_event_projection_args(payload=payload)
        if not args:
            return {"applied": False, "reason": "no_projection_for_event"}
        try:
            projection_result = await self._call_tool(name=tool_name, arguments=args)
            projection_error = self._tool_error_message(projection_result)
            if projection_error:
                log_trace_event(
                    event_type="crm_projection_failed",
                    trace_id=trace_id,
                    lead_id=lead_id,
                    status="failure",
                    payload={"tool_name": tool_name},
                    error={"error_message": projection_error},
                )
                return {
                    "applied": False,
                    "error": projection_error,
                    "tool_result": projection_result,
                }
            log_trace_event(
                event_type="crm_projection_applied",
                trace_id=trace_id,
                lead_id=lead_id,
                status="success",
                payload={"tool_name": tool_name},
            )
            return {"applied": True}
        except Exception as exc:  # pragma: no cover - defensive best-effort branch
            log_trace_event(
                event_type="crm_projection_failed",
                trace_id=trace_id,
                lead_id=lead_id,
                status="failure",
                payload={"tool_name": tool_name},
                error={"error_message": str(exc)},
            )
            return {"applied": False, "error": str(exc)}

    async def _resolve_tool_name(self, *, operation: str) -> str | None:
        if operation == "upsert_lead":
            configured = self._settings.hubspot_mcp_tool_upsert_lead.strip()
            if configured:
                return configured
        if operation == "append_event":
            configured = self._settings.hubspot_mcp_tool_append_event.strip()
            if configured:
                return configured

        tools = await self._list_tools()
        if not tools:
            return None
        names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
        names = [name for name in names if isinstance(name, str) and name.strip()]
        if not names:
            return None

        # SPEC-GAP: HubSpot remote MCP tool names/arg schemas are account-scoped and
        # are not defined in specs/api contracts for this repo.
        patterns = (
            [
                r"\bupsert\b.*\bcontact\b",
                r"\bcreate(?:_or_)?update\b.*\bcontact\b",
                r"\bcreate\b.*\bcontact\b",
                r"\bupdate\b.*\bcontact\b",
            ]
            if operation == "upsert_lead"
            else [
                r"\bcreate\b.*\bnote\b",
                r"\bappend\b.*\bevent\b",
                r"\bcreate\b.*\bengagement\b",
                r"\blog\b.*\bactivity\b",
            ]
        )
        for pattern in patterns:
            regex = re.compile(pattern)
            for name in names:
                if regex.search(name.lower()):
                    return name
        if "manage_crm_objects" in names:
            return "manage_crm_objects"
        return None

    async def _prepare_tool_arguments(
        self,
        *,
        tool_name: str,
        operation: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name != "manage_crm_objects":
            return payload
        if operation == "upsert_lead":
            return await self._build_manage_upsert_args(payload=payload)
        if operation == "append_event":
            return await self._build_manage_event_args(payload=payload)
        return payload

    async def _build_manage_upsert_args(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        lead = payload.get("lead", {}) if isinstance(payload, dict) else {}
        if not isinstance(lead, dict):
            raise ValueError("Lead payload is missing for HubSpot upsert.")

        lead_id = self._coerce_str(lead.get("lead_id")) or ""
        company_name = self._coerce_str(lead.get("company_name"))
        company_domain = self._coerce_str(lead.get("company_domain"))
        company_id = self._coerce_str(lead.get("company_id"))
        segment = self._coerce_str(lead.get("segment"))
        alt_segment = self._coerce_str(lead.get("alternate_segment"))
        segment_confidence = lead.get("segment_confidence")
        ai_maturity_score = lead.get("ai_maturity_score")

        if not company_name and not company_domain:
            raise ValueError("CRM lead upsert requires company_name or company_domain.")

        description_parts = [f"lead_id={lead_id}"]
        if company_id:
            description_parts.append(f"company_id={company_id}")
        if segment:
            description_parts.append(f"segment={segment}")
        if alt_segment:
            description_parts.append(f"alternate_segment={alt_segment}")
        if segment_confidence is not None:
            description_parts.append(f"segment_confidence={segment_confidence}")
        if ai_maturity_score is not None:
            description_parts.append(f"ai_maturity_score={ai_maturity_score}")

        properties: dict[str, str] = {}
        if company_name:
            properties["name"] = company_name
        if company_domain:
            properties["domain"] = company_domain
        properties["description"] = "; ".join(description_parts)

        maybe_object_id = await self._find_company_by_domain_or_name(domain=company_domain, name=company_name)
        if maybe_object_id is not None:
            return {
                "updateRequest": {
                    "objects": [
                        {
                            "objectType": "companies",
                            "objectId": maybe_object_id,
                            "properties": properties,
                        }
                    ]
                },
                "confirmationStatus": "CONFIRMATION_WAIVED_FOR_SESSION",
            }

        return {
            "createRequest": {
                "objects": [
                    {
                        "objectType": "companies",
                        "properties": properties,
                    }
                ]
            },
            "confirmationStatus": "CONFIRMATION_WAIVED_FOR_SESSION",
        }

    async def _build_manage_event_args(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        lead_id = self._coerce_str(payload.get("lead_id")) if isinstance(payload, dict) else None
        event_type = self._coerce_str(payload.get("event_type")) if isinstance(payload, dict) else None
        event_key = self._coerce_str(payload.get("event_key")) if isinstance(payload, dict) else None
        event_payload = payload.get("payload", {}) if isinstance(payload, dict) else {}
        anchor_company_id = await self._ensure_event_anchor_company(lead_id=lead_id)
        note_body = self._render_event_note_body(
            lead_id=lead_id,
            event_type=event_type,
            event_key=event_key,
            event_payload=event_payload,
        )

        return {
            "createRequest": {
                "objects": [
                    {
                        "objectType": "notes",
                        "properties": {
                            "hs_note_body": note_body,
                        },
                        "associations": [
                            {
                                "targetObjectId": anchor_company_id,
                                "targetObjectType": "companies",
                            }
                        ],
                    }
                ]
            },
            "confirmationStatus": "CONFIRMATION_WAIVED_FOR_SESSION",
        }

    async def _build_manage_event_projection_args(self, *, payload: dict[str, Any]) -> dict[str, Any] | None:
        lead_id = self._coerce_str(payload.get("lead_id")) if isinstance(payload, dict) else None
        event_type = self._coerce_str(payload.get("event_type")) if isinstance(payload, dict) else None
        event_payload = payload.get("payload", {}) if isinstance(payload, dict) else {}
        if not lead_id or not event_type:
            return None
        if not isinstance(event_payload, dict):
            return None

        anchor_company_id = await self._ensure_event_anchor_company(lead_id=lead_id)
        properties = self._event_projection_properties(event_type=event_type, event_payload=event_payload)
        if not properties:
            return None
        return {
            "updateRequest": {
                "objects": [
                    {
                        "objectType": "companies",
                        "objectId": anchor_company_id,
                        "properties": properties,
                    }
                ]
            },
            "confirmationStatus": "CONFIRMATION_WAIVED_FOR_SESSION",
        }

    def _event_projection_properties(self, *, event_type: str, event_payload: dict[str, Any]) -> dict[str, str]:
        properties: dict[str, str] = {}
        if event_type == "booking_confirmed":
            booking_id = HubSpotMCPService._coerce_str(event_payload.get("booking_id")) or "unknown"
            starts_at = HubSpotMCPService._coerce_str(event_payload.get("starts_at")) or "unknown_start"
            ends_at = HubSpotMCPService._coerce_str(event_payload.get("ends_at")) or "unknown_end"
            timezone = HubSpotMCPService._coerce_str(event_payload.get("timezone")) or "unknown_tz"
            calendar_ref = HubSpotMCPService._coerce_str(event_payload.get("calendar_ref")) or ""
            booking_status = HubSpotMCPService._coerce_str(event_payload.get("status")) or "confirmed"
            description = f"last_booking={booking_id}; starts_at={starts_at}; timezone={timezone}"
            if calendar_ref:
                description += f"; meeting_url={calendar_ref}"
            properties["description"] = description
            self._set_property_if_configured(
                properties,
                self._settings.hubspot_company_prop_last_booking_id,
                booking_id,
            )
            self._set_property_if_configured(
                properties,
                self._settings.hubspot_company_prop_last_booking_start_at,
                starts_at,
            )
            self._set_property_if_configured(
                properties,
                self._settings.hubspot_company_prop_last_booking_end_at,
                ends_at,
            )
            self._set_property_if_configured(
                properties,
                self._settings.hubspot_company_prop_last_booking_timezone,
                timezone,
            )
            self._set_property_if_configured(
                properties,
                self._settings.hubspot_company_prop_last_booking_url,
                calendar_ref,
            )
            self._set_property_if_configured(
                properties,
                self._settings.hubspot_company_prop_last_booking_status,
                booking_status,
            )
            return properties

        if event_type == "enrichment_updated":
            funding = HubSpotMCPService._coerce_str(event_payload.get("funding_signal_summary")) or "n/a"
            hiring = HubSpotMCPService._coerce_str(event_payload.get("job_velocity_summary")) or "n/a"
            leadership = HubSpotMCPService._coerce_str(event_payload.get("leadership_signal_summary")) or "n/a"
            properties["description"] = f"enrichment: funding={funding}; hiring={hiring}; leadership={leadership}"
            return properties

        return {}

    @staticmethod
    def _set_property_if_configured(properties: dict[str, str], property_name: str, value: str) -> None:
        key = property_name.strip()
        if not key or not value:
            return
        properties[key] = value

    @staticmethod
    def _render_event_note_body(
        *,
        lead_id: str | None,
        event_type: str | None,
        event_key: str | None,
        event_payload: Any,
    ) -> str:
        if isinstance(event_payload, dict) and event_type == "booking_confirmed":
            booking_id = HubSpotMCPService._coerce_str(event_payload.get("booking_id")) or "unknown"
            starts_at = HubSpotMCPService._coerce_str(event_payload.get("starts_at")) or "unknown"
            ends_at = HubSpotMCPService._coerce_str(event_payload.get("ends_at")) or "unknown"
            timezone = HubSpotMCPService._coerce_str(event_payload.get("timezone")) or "unknown"
            calendar_ref = HubSpotMCPService._coerce_str(event_payload.get("calendar_ref")) or "n/a"
            return (
                f"Booking confirmed\n"
                f"Lead: {lead_id or 'n/a'}\n"
                f"Event key: {event_key or 'n/a'}\n"
                f"Booking ID: {booking_id}\n"
                f"Start: {starts_at}\n"
                f"End: {ends_at}\n"
                f"Timezone: {timezone}\n"
                f"Meeting URL: {calendar_ref}"
            )

        if isinstance(event_payload, dict) and event_type == "enrichment_updated":
            funding = HubSpotMCPService._coerce_str(event_payload.get("funding_signal_summary")) or "n/a"
            hiring = HubSpotMCPService._coerce_str(event_payload.get("job_velocity_summary")) or "n/a"
            layoffs = HubSpotMCPService._coerce_str(event_payload.get("layoffs_signal_summary")) or "n/a"
            leadership = HubSpotMCPService._coerce_str(event_payload.get("leadership_signal_summary")) or "n/a"
            return (
                f"Enrichment updated\n"
                f"Lead: {lead_id or 'n/a'}\n"
                f"Event key: {event_key or 'n/a'}\n"
                f"Funding: {funding}\n"
                f"Hiring: {hiring}\n"
                f"Layoffs: {layoffs}\n"
                f"Leadership: {leadership}"
            )

        summary = {
            "lead_id": lead_id,
            "event_type": event_type,
            "event_key": event_key,
            "payload": event_payload,
        }
        return json.dumps(summary, ensure_ascii=True)

    async def _ensure_event_anchor_company(self, *, lead_id: str | None) -> int:
        if not lead_id:
            raise ValueError("Booking/event payload is missing lead_id, cannot build HubSpot associations.")

        anchor_name = f"Lead {lead_id}"
        existing_id = await self._find_company_by_domain_or_name(domain=None, name=anchor_name)
        if existing_id is not None:
            return existing_id

        create_args = {
            "createRequest": {
                "objects": [
                    {
                        "objectType": "companies",
                        "properties": {
                            "name": anchor_name,
                            "description": f"event_anchor_for_lead_id={lead_id}",
                        },
                    }
                ]
            },
            "confirmationStatus": "CONFIRMATION_WAIVED_FOR_SESSION",
        }
        create_result = await self._call_tool(name="manage_crm_objects", arguments=create_args)
        if self._tool_error_message(create_result):
            raise _MCPCallError(
                "HubSpot MCP manage_crm_objects failed while creating event anchor company.",
                retryable=False,
                details={"tool_name": "manage_crm_objects", "tool_result": create_result},
            )
        record_id, _ = self._extract_ids(create_result)
        if record_id and record_id.isdigit():
            return int(record_id)

        for obj in self._extract_content_objects(create_result):
            create_results = obj.get("createResults")
            if not isinstance(create_results, dict):
                continue
            results = create_results.get("results")
            if not isinstance(results, list):
                continue
            for item in results:
                if not isinstance(item, dict):
                    continue
                object_id = item.get("objectId")
                if isinstance(object_id, int) and object_id > 0:
                    return object_id
                if isinstance(object_id, str) and object_id.strip().isdigit():
                    return int(object_id.strip())

        # Fallback lookup in case create response omits explicit IDs.
        fallback_id = await self._find_company_by_domain_or_name(domain=None, name=anchor_name)
        if fallback_id is not None:
            return fallback_id
        raise _MCPCallError(
            "HubSpot MCP created event anchor company but did not return a resolvable company id.",
            retryable=False,
            details={"tool_result": create_result},
        )

    async def _find_company_by_domain_or_name(self, *, domain: str | None, name: str | None) -> int | None:
        filters: list[dict[str, Any]] = []
        if domain:
            filters.append({"propertyName": "domain", "operator": "EQ", "value": domain})
        if not filters and name:
            filters.append({"propertyName": "name", "operator": "EQ", "value": name})
        if not filters:
            return None

        search_args = {
            "objectType": "companies",
            "filterGroups": [{"filters": filters}],
            "limit": 1,
            "properties": ["name", "domain"],
            "chatInsights": {
                "userIntent": "<unchanged>",
                "satisfaction": "NEUTRAL",
            },
        }
        search_result = await self._call_tool(name="search_crm_objects", arguments=search_args)
        if self._tool_error_message(search_result):
            raise _MCPCallError(
                "HubSpot MCP search_crm_objects failed during upsert preparation.",
                retryable=False,
                details={"tool_name": "search_crm_objects", "tool_result": search_result},
            )

        for obj in self._extract_content_objects(search_result):
            for key in ("results", "objects", "items", "data"):
                records = obj.get(key)
                if not isinstance(records, list):
                    continue
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    record_id = record.get("id")
                    if isinstance(record_id, int) and record_id > 0:
                        return record_id
                    if isinstance(record_id, str) and record_id.strip().isdigit():
                        return int(record_id.strip())
        return None

    async def _list_tools(self) -> list[dict[str, Any]]:
        if self._tools_cache is not None:
            return self._tools_cache

        await self._ensure_initialized()
        request_id = self._next_request_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
        }
        _, parsed = await self._post_rpc(payload=payload, expect_result=True, allow_refresh=True)
        message = self._extract_rpc_result(parsed=parsed, request_id=request_id)
        result = message.get("result", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        if isinstance(tools, list):
            self._tools_cache = [tool for tool in tools if isinstance(tool, dict)]
            return self._tools_cache
        return []

    async def _call_tool(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_initialized()
        request_id = self._next_request_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }
        _, parsed = await self._post_rpc(payload=payload, expect_result=True, allow_refresh=True)
        message = self._extract_rpc_result(parsed=parsed, request_id=request_id)
        result = message.get("result", {})
        return result if isinstance(result, dict) else {"result": result}

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            request_id = self._next_request_id()
            initialize_request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": self._protocol_version,
                    "capabilities": {"roots": {"listChanged": False}},
                    "clientInfo": {"name": "conversion-engine", "version": "1.0.0"},
                },
            }
            response, parsed = await self._post_rpc(
                payload=initialize_request,
                expect_result=True,
                include_session=False,
                allow_refresh=True,
            )
            message = self._extract_rpc_result(parsed=parsed, request_id=request_id)
            result = message.get("result", {})
            if isinstance(result, dict):
                server_version = result.get("protocolVersion")
                if isinstance(server_version, str) and server_version.strip():
                    self._protocol_version = server_version.strip()

            session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
            if isinstance(session_id, str) and session_id.strip():
                self._session_id = session_id.strip()

            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
            await self._post_rpc(payload=initialized_notification, expect_result=False, allow_refresh=True)
            self._initialized = True

    async def _post_rpc(
        self,
        *,
        payload: dict[str, Any],
        expect_result: bool,
        include_session: bool = True,
        allow_refresh: bool = True,
    ) -> tuple[httpx.Response, Any]:
        access_token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self._protocol_version,
        }
        if include_session and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        response = await self._post_json(url=self._server_url, headers=headers, payload=payload)
        if response.status_code == 401 and allow_refresh and self._can_refresh():
            await self._refresh_access_token(force=True)
            refreshed_headers = dict(headers)
            refreshed_headers["Authorization"] = f"Bearer {self._access_token}"
            response = await self._post_json(url=self._server_url, headers=refreshed_headers, payload=payload)
        if not response.is_success:
            parsed = self._safe_json(response)
            raise _MCPCallError(
                f"HubSpot MCP returned HTTP {response.status_code}.",
                retryable=response.status_code >= 500,
                details={"response": parsed},
            )

        if not expect_result:
            return response, {}

        parsed = self._parse_rpc_payload(response)
        return response, parsed

    async def _post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(url, headers=headers, json=payload)
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            return await client.post(url, headers=headers, json=payload)

    async def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        if self._can_refresh():
            await self._refresh_access_token(force=True)
            if self._access_token:
                return self._access_token
        raise ValueError(
            "HubSpot MCP auth is not configured. Set HUBSPOT_MCP_ACCESS_TOKEN, "
            "or set HUBSPOT_MCP_REFRESH_TOKEN + HUBSPOT_MCP_CLIENT_ID + HUBSPOT_MCP_CLIENT_SECRET."
        )

    def _can_refresh(self) -> bool:
        return bool(self._refresh_token and self._client_id and self._client_secret)

    async def _refresh_access_token(self, *, force: bool) -> None:
        async with self._refresh_lock:
            if self._access_token and not force:
                return
            if not self._can_refresh():
                raise ValueError(
                    "HubSpot access token is missing, and refresh credentials are incomplete. "
                    "Set HUBSPOT_MCP_REFRESH_TOKEN, HUBSPOT_MCP_CLIENT_ID, and HUBSPOT_MCP_CLIENT_SECRET."
                )

            data = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            if self._http_client is not None:
                response = await self._http_client.post(self._oauth_token_url, headers=headers, data=data)
            else:
                async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
                    response = await client.post(self._oauth_token_url, headers=headers, data=data)

            if not response.is_success:
                raise _MCPCallError(
                    f"HubSpot OAuth token refresh failed with HTTP {response.status_code}.",
                    retryable=response.status_code >= 500,
                    details={"response": self._safe_json(response)},
                )
            raw = self._safe_json(response)
            access_token = raw.get("access_token") or raw.get("accessToken")
            if not isinstance(access_token, str) or not access_token.strip():
                raise ValueError("HubSpot OAuth token refresh succeeded but access_token was missing in the response.")
            self._access_token = access_token.strip()

            refreshed_token = raw.get("refresh_token") or raw.get("refreshToken")
            if isinstance(refreshed_token, str) and refreshed_token.strip():
                self._refresh_token = refreshed_token.strip()

    def _next_request_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    @staticmethod
    def _validated_server_url(value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("HubSpot MCP URL must be a valid absolute URL.")
        return value.rstrip("/")

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            parsed = response.json()
            return parsed if isinstance(parsed, dict) else {"payload": parsed}
        except ValueError:
            text = response.text.strip()
            if not text:
                return {}
            return {"text": text[:2000]}

    @staticmethod
    def _parse_rpc_payload(response: httpx.Response) -> Any:
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" in content_type:
            try:
                return response.json()
            except ValueError as exc:
                raise _MCPCallError(
                    "HubSpot MCP returned non-JSON payload for JSON response.",
                    retryable=True,
                    details={"text": response.text[:2000]},
                ) from exc
        if "text/event-stream" in content_type:
            return HubSpotMCPService._parse_sse_events(response.text)
        try:
            return response.json()
        except ValueError:
            raise _MCPCallError(
                "HubSpot MCP returned an unsupported response content type.",
                retryable=True,
                details={"content_type": content_type, "text": response.text[:2000]},
            )

    @staticmethod
    def _parse_sse_events(payload: str) -> list[Any]:
        events: list[Any] = []
        data_lines: list[str] = []
        for raw_line in payload.splitlines():
            line = raw_line.rstrip("\r")
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
                continue
            if line == "":
                if data_lines:
                    blob = "\n".join(data_lines).strip()
                    if blob and blob != "[DONE]":
                        try:
                            events.append(json.loads(blob))
                        except json.JSONDecodeError:
                            events.append({"text": blob})
                    data_lines = []
        if data_lines:
            blob = "\n".join(data_lines).strip()
            if blob and blob != "[DONE]":
                try:
                    events.append(json.loads(blob))
                except json.JSONDecodeError:
                    events.append({"text": blob})
        return events

    @staticmethod
    def _tool_error_message(tool_result: dict[str, Any]) -> str | None:
        if not bool(tool_result.get("isError")):
            return None
        content = tool_result.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if not isinstance(text, str):
                    continue
                stripped = text.strip()
                if not stripped:
                    continue
                if stripped.startswith("{"):
                    try:
                        parsed = json.loads(stripped)
                    except ValueError:
                        return stripped[:500]
                    if isinstance(parsed, dict):
                        message = parsed.get("errorMessage") or parsed.get("message") or parsed.get("error")
                        if message:
                            return str(message)
                return stripped[:500]
        return "unknown tool error"

    @staticmethod
    def _extract_rpc_result(*, parsed: Any, request_id: int) -> dict[str, Any]:
        messages = parsed if isinstance(parsed, list) else [parsed]
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise _MCPCallError(
                    "HubSpot MCP JSON-RPC request failed.",
                    retryable=False,
                    details={"error": message.get("error")},
                )
            if "result" in message:
                return message
        raise _MCPCallError(
            "HubSpot MCP did not return a JSON-RPC result for the request.",
            retryable=True,
            details={"response": parsed},
        )

    @staticmethod
    def _extract_ids(tool_result: dict[str, Any]) -> tuple[str | None, str | None]:
        candidate_objects = HubSpotMCPService._extract_content_objects(tool_result)

        record_id = HubSpotMCPService._extract_first(
            candidate_objects,
            "record_id",
            "crm_record_id",
            "lead_id",
            "id",
            "object_id",
            "objectId",
        )
        event_id = HubSpotMCPService._extract_first(
            candidate_objects,
            "event_id",
            "crm_event_id",
            "activity_id",
            "engagement_id",
            "id",
            "objectId",
        )
        return record_id, event_id

    @staticmethod
    def _extract_content_objects(tool_result: dict[str, Any]) -> list[dict[str, Any]]:
        candidate_objects: list[dict[str, Any]] = [tool_result]

        structured = tool_result.get("structuredContent")
        if isinstance(structured, dict):
            candidate_objects.append(structured)

        content = tool_result.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if not isinstance(text, str):
                    continue
                stripped = text.strip()
                if not stripped or not stripped.startswith("{"):
                    continue
                try:
                    parsed = json.loads(stripped)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    candidate_objects.append(parsed)

        # Flatten common nested result containers used by HubSpot MCP writes.
        for obj in list(candidate_objects):
            create_results = obj.get("createResults")
            if isinstance(create_results, dict):
                results = create_results.get("results")
                if isinstance(results, list):
                    candidate_objects.extend(item for item in results if isinstance(item, dict))
            update_results = obj.get("updateResults")
            if isinstance(update_results, dict):
                results = update_results.get("results")
                if isinstance(results, list):
                    candidate_objects.extend(item for item in results if isinstance(item, dict))
        return candidate_objects

    @staticmethod
    def _extract_first(objects: list[dict[str, Any]], *keys: str) -> str | None:
        for key in keys:
            for obj in objects:
                value = obj.get(key)
                coerced = HubSpotMCPService._coerce_str(value)
                if coerced:
                    return coerced
        return None

    @staticmethod
    def _coerce_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def map_enrichment_to_crm_payload(*, lead_id: str, enrichment_artifact: dict[str, Any]) -> CRMEnrichmentPayload:
    """Map normalized enrichment artifact into CRM enrichment fields."""
    signals = enrichment_artifact.get("signals", {}) if isinstance(enrichment_artifact, dict) else {}

    def summary(path: str) -> str | None:
        signal = signals.get(path)
        if not isinstance(signal, dict):
            return None
        raw_summary = signal.get("summary")
        if isinstance(raw_summary, dict):
            return str(raw_summary)
        if isinstance(raw_summary, str):
            return raw_summary
        return None

    return CRMEnrichmentPayload(
        lead_id=lead_id,
        funding_signal_summary=summary("crunchbase"),
        job_velocity_summary=summary("job_posts"),
        layoffs_signal_summary=summary("layoffs"),
        leadership_signal_summary=summary("leadership_changes"),
        bench_match_status=enrichment_artifact.get("bench_match_status"),
        brief_references=list(enrichment_artifact.get("brief_references", [])),
        raw=enrichment_artifact,
    )
