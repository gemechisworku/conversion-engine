"""Runtime orchestration handlers aligned to orchestration API contracts."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent.config.settings import Settings
from agent.graphs.lead_intake_langgraph import LeadIntakeGraphDeps, compile_lead_intake_graph
from agent.graphs.reply_langgraph import ReplyRouteGraphDeps, compile_reply_route_graph
from agent.graphs.state import LeadGraphState
from agent.graphs.transitions import InvalidStateTransitionError, validate_lead_transition
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.common.schemas import ErrorEnvelope
from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.conversation.email_llm import InboundEmailInterpretLLM
from agent.services.email.client import EmailService
from agent.services.email.rfc_ids import merge_references_header, normalize_message_id
from agent.services.email.schemas import OutboundEmailRequest
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.services.observability.events import log_processing_step, log_trace_event
from agent.services.observability.langfuse_llm import langfuse_workflow_span
from agent.services.orchestration.schemas import (
    LeadAdvanceRequest,
    LeadCompactRequest,
    LeadEscalationRequest,
    LeadProcessRequest,
    LeadRehydrateRequest,
    LeadReplyRequest,
    MemorySessionWriteRequest,
    OutreachDraftRequest,
    OutreachReviewRequest,
    OutreachSendRequest,
    ResponseEnvelope,
)
from agent.services.outreach.outreach_flow import OutreachFlowDeps, run_outreach_draft_only, run_outreach_review_for_lead, run_outreach_send_for_lead
from agent.services.outreach.outreach_payload import parse_outreach_stored
from agent.services.policy.outbound_policy import OutboundPolicyService

class OrchestrationRuntime:
    # Implements: FR-9, FR-11, FR-12, FR-14, FR-15
    # Workflow: reply_handling.md
    # Schema: session_state.md
    # API: orchestration_api.md
    def __init__(
        self,
        *,
        settings: Settings,
        state_repo: SQLiteStateRepository,
        enrichment_services: dict[str, Any],
        hubspot_service: HubSpotMCPService | None = None,
        email_service: EmailService | None = None,
    ) -> None:
        self._settings = settings
        self._state_repo = state_repo
        self._enrichment_services = enrichment_services
        self._hubspot = hubspot_service
        self._email_service = email_service
        self._policy = OutboundPolicyService(settings)
        self._lead_intake_graph = compile_lead_intake_graph(
            LeadIntakeGraphDeps(
                hubspot=self._hubspot,
                enrichment_services=self._enrichment_services,
                state_repo=self._state_repo,
            )
        )
        llm = enrichment_services.get("llm")
        self._reply_route_graph = compile_reply_route_graph(
            ReplyRouteGraphDeps(settings=settings, llm=llm, state_repo=state_repo)
        )

    async def process_lead(self, request: LeadProcessRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_orch_{uuid4().hex[:12]}"
        lead_id = self._lead_id_for_company(company_id=request.company_id)
        company_name = str(request.metadata.get("company_name") or request.company_id)
        company_domain = str(request.metadata.get("company_domain") or "")
        log_processing_step(
            component="orchestration",
            step="process_lead.start",
            message="Processing new lead",
            lead_id=lead_id,
            trace_id=trace_id,
            company_id=request.company_id,
            company_name=company_name,
            company_domain=company_domain,
            idempotency_key=request.idempotency_key,
        )
        cached = self._state_repo.get_idempotency_response(idempotency_key=request.idempotency_key)
        if cached is not None:
            return ResponseEnvelope.model_validate(cached)
        try:
            self._state_repo.upsert_pipeline_run_start(
                lead_id=lead_id,
                company_id=request.company_id,
                company_name=company_name,
                company_domain=company_domain,
                trace_id=trace_id,
            )
            self._state_repo.upsert_session_state(
                lead_id=lead_id,
                payload={
                    "current_stage": "new_lead",
                    "next_best_action": "enrich",
                    "current_objective": "process_lead",
                    "pending_actions": [],
                    "policy_flags": [],
                    "handoff_required": False,
                },
            )
            validate_lead_transition(from_state="new_lead", to_state="enriching")
            self._state_repo.upsert_session_state(
                lead_id=lead_id,
                payload={
                    "current_stage": "enriching",
                    "next_best_action": "enrich",
                    "current_objective": "collect_research",
                    "pending_actions": [],
                    "policy_flags": [],
                    "handoff_required": False,
                },
            )
            state = LeadGraphState(lead_id=lead_id, company_id=request.company_id, current_stage="enriching")
            log_processing_step(
                component="orchestration",
                step="process_lead.graph",
                message="Invoking lead intake LangGraph (intake → enrich → crm_sync)",
                lead_id=lead_id,
                trace_id=trace_id,
                hubspot_configured=self._hubspot is not None,
            )
            if self._hubspot is not None:
                readiness = await self._hubspot.verify_tool_readiness()
                if not readiness.get("ready", False):
                    return self._failure(
                        request_id=request_id,
                        trace_id=trace_id,
                        code="CONFIG_ERROR",
                        message=f"HubSpot MCP readiness failed: {readiness}",
                        retryable=False,
                    )
            with langfuse_workflow_span(
                self._settings,
                trace_id=trace_id,
                lead_id=lead_id,
                name="graphs.lead_intake",
            ):
                graph_out = await self._lead_intake_graph.ainvoke(
                    {
                        "lead_id": lead_id,
                        "company_id": request.company_id,
                        "company_name": company_name,
                        "company_domain": company_domain,
                        "trace_id": trace_id,
                        "idempotency_key": request.idempotency_key,
                        "lead_state": state.model_dump(mode="json"),
                        "errors": [],
                    }
                )
            enriched_state = LeadGraphState.model_validate(graph_out["enriched_state"])
            artifact = EnrichmentArtifact.model_validate(graph_out["artifact"])
            log_processing_step(
                component="orchestration",
                step="process_lead.graph_done",
                message="Lead intake graph completed; persisting session and conversation state",
                lead_id=lead_id,
                trace_id=trace_id,
                crm_synced=graph_out.get("crm_synced"),
                brief_refs_count=len(enriched_state.brief_refs),
                artifact_company_id=artifact.company_id,
            )
            self._state_repo.upsert_session_state(
                lead_id=lead_id,
                payload={
                    "current_stage": enriched_state.current_stage,
                    "next_best_action": enriched_state.next_best_action,
                    "current_objective": "generate_outreach",
                    "brief_refs": enriched_state.brief_refs,
                    "pending_actions": [{"action_type": "draft_outreach", "status": "pending"}],
                    "policy_flags": enriched_state.policy_flags,
                    "handoff_required": False,
                },
            )
            self._state_repo.upsert_conversation_state(
                lead_id=lead_id,
                payload={
                    "current_stage": "outbound_prepared",
                    "current_channel": "email",
                    "last_customer_intent": "unknown",
                    "last_customer_sentiment": "uncertain",
                    "qualification_status": "unknown",
                    "pending_actions": [{"action_type": "send_first_outreach", "status": "pending"}],
                    "policy_flags": [],
                    "scheduling_context": {"booking_status": "none", "timezone": None, "slots_proposed": []},
                },
            )
            self._state_repo.update_pipeline_run_stage(
                lead_id=lead_id,
                stage=enriched_state.current_stage,
                trace_id=trace_id,
            )

            log_trace_event(
                event_type="lead_processed",
                trace_id=trace_id,
                lead_id=lead_id,
                status="success",
                payload={"company_id": request.company_id},
            )
            env = ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={"lead_id": lead_id, "state": "brief_ready"},
            )
            self._state_repo.put_idempotency_response(
                idempotency_key=request.idempotency_key,
                response=env.model_dump(mode="json"),
            )
            return env
        except InvalidStateTransitionError as exc:
            self._state_repo.update_pipeline_run_stage(
                lead_id=lead_id,
                stage="failed_invalid_transition",
                trace_id=trace_id,
            )
            log_processing_step(
                component="orchestration",
                step="process_lead.error",
                message="Invalid state transition during process_lead",
                lead_id=lead_id,
                trace_id=trace_id,
                error=str(exc),
                level=logging.WARNING,
            )
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_STATE_TRANSITION",
                message=str(exc),
                retryable=False,
            )
        except Exception as exc:  # pragma: no cover - orchestration guard
            self._state_repo.update_pipeline_run_stage(
                lead_id=lead_id,
                stage="failed",
                trace_id=trace_id,
            )
            log_processing_step(
                component="orchestration",
                step="process_lead.error",
                message="Unhandled exception during process_lead",
                lead_id=lead_id,
                trace_id=trace_id,
                error=str(exc),
                level=logging.ERROR,
            )
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="ORCHESTRATION_FAILED",
                message=str(exc),
                retryable=True,
            )

    async def handle_reply(self, request: LeadReplyRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_reply_{uuid4().hex[:12]}"
        log_processing_step(
            component="orchestration",
            step="handle_reply.start",
            message="Inbound reply received",
            lead_id=request.lead_id,
            trace_id=trace_id,
            channel=request.channel,
            message_id=request.message_id,
            idempotency_key=request.idempotency_key,
        )
        session = self._state_repo.get_session_state(lead_id=request.lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{request.lead_id}'.",
                retryable=False,
            )
        cached = self._state_repo.get_idempotency_response(idempotency_key=request.idempotency_key)
        if cached is not None:
            return ResponseEnvelope.model_validate(cached)
        try:
            validate_lead_transition(from_state=session["current_stage"], to_state="reply_received")
            if request.channel.lower() == "email":
                self._state_repo.ensure_email_thread(lead_id=request.lead_id)
            self._state_repo.append_message(
                lead_id=request.lead_id,
                channel=request.channel,
                message_id=request.message_id,
                direction="inbound",
                content=request.content,
                metadata={
                    "received_at": request.received_at.isoformat(),
                    "subject": request.subject,
                    "rfc_message_id": request.rfc_message_id,
                    "references_for_thread": request.references_for_thread,
                },
            )
            if request.channel.lower() == "email" and request.rfc_message_id:
                self._state_repo.email_thread_record_inbound(
                    lead_id=request.lead_id,
                    inbound_rfc_message_id=request.rfc_message_id,
                    prior_references_fragment=request.references_for_thread,
                )
            act2_context = await self._run_act2_enrichment_before_reply(
                lead_id=request.lead_id,
                request=request,
            )
            log_processing_step(
                component="orchestration",
                step="handle_reply.act2",
                message="Act II pre-reply enrichment finished" if act2_context else "Act II pipeline skipped or disabled",
                lead_id=request.lead_id,
                trace_id=trace_id,
                act2_ran=act2_context is not None,
            )
            briefs_all = self._state_repo.get_briefs(lead_id=request.lead_id) or {}
            hiring = briefs_all.get("hiring_signal_brief")
            hiring_dict = hiring if isinstance(hiring, dict) else {}
            with langfuse_workflow_span(
                self._settings,
                trace_id=trace_id,
                lead_id=request.lead_id,
                name="graphs.reply_route",
            ):
                route_out = await self._reply_route_graph.ainvoke(
                    {
                        "lead_id": request.lead_id,
                        "trace_id": trace_id,
                        "channel": request.channel,
                        "content": request.content,
                        "subject": request.subject,
                        "company_name": request.company_name or "",
                        "hiring_signal_brief": hiring_dict,
                        "recent_outbound_snippet": self._recent_outbound_email_snippet(lead_id=request.lead_id),
                    }
                )
            intent = str(route_out.get("intent") or "unclear")
            next_action = str(route_out.get("next_action") or "clarify")
            next_state = str(route_out.get("next_state") or "qualifying")
            raw_interp = route_out.get("email_interp")
            email_interp: InboundEmailInterpretLLM | None = None
            if isinstance(raw_interp, dict):
                try:
                    email_interp = InboundEmailInterpretLLM.model_validate(raw_interp)
                except Exception:
                    email_interp = None
            if email_interp is not None and request.channel.lower() == "email":
                in_reply_to_hdr, refs_hdr = self._state_repo.get_email_thread_reply_headers(
                    lead_id=request.lead_id
                )
                reply_target = normalize_message_id(request.rfc_message_id) or normalize_message_id(
                    in_reply_to_hdr
                )
                refs_combined = merge_references_header(refs_hdr, reply_target)
                thread_id = self._state_repo.ensure_email_thread(lead_id=request.lead_id)
                self._state_repo.append_message(
                    lead_id=request.lead_id,
                    channel="email",
                    message_id=f"suggested_email_reply_{uuid4().hex[:12]}",
                    direction="outbound",
                    content=email_interp.suggested_reply_body,
                    metadata={
                        "kind": "suggested_reply_email",
                        "subject": email_interp.suggested_reply_subject,
                        "reply_to_message_id": request.message_id,
                        "intent": intent,
                        "llm_confidence": email_interp.confidence,
                        "in_reply_to": reply_target,
                        "references": refs_combined or None,
                        "email_thread_id": thread_id,
                    },
                )
            log_processing_step(
                component="orchestration",
                step="handle_reply.route",
                message="Classified inbound intent and next action",
                lead_id=request.lead_id,
                trace_id=trace_id,
                intent=intent,
                next_action=next_action,
                next_state=next_state,
                channel=request.channel,
                llm_email=email_interp is not None,
            )
            validate_lead_transition(from_state="reply_received", to_state=next_state)

            self._state_repo.upsert_session_state(
                lead_id=request.lead_id,
                payload={
                    "current_stage": next_state,
                    "next_best_action": next_action,
                    "current_objective": "reply_handling",
                    "brief_refs": [
                        *session.get("brief_refs", []),
                        *(
                            [
                                act2_context.enrichment_brief.brief_id,
                                act2_context.compliance_brief.brief_id,
                                act2_context.news_brief.brief_id,
                            ]
                            if act2_context is not None
                            else []
                        ),
                    ],
                    "pending_actions": route_out.get("branch_pending")
                    or [{"action_type": next_action, "status": "pending"}],
                    "policy_flags": session.get("policy_flags", []),
                    "handoff_required": next_state == "handoff_required",
                },
            )
            self._state_repo.upsert_conversation_state(
                lead_id=request.lead_id,
                payload={
                    "current_stage": "inbound_received",
                    "current_channel": request.channel,
                    "last_inbound_message_id": request.message_id,
                    "last_customer_intent": intent,
                    "last_customer_sentiment": "neutral",
                    "qualification_status": (
                        "likely_qualified"
                        if (intent in {"interest", "schedule"} or next_action == "schedule")
                        else "unknown"
                    ),
                    "pending_actions": route_out.get("branch_pending")
                    or [{"action_type": next_action, "status": "pending"}],
                    "policy_flags": [],
                    "scheduling_context": {"booking_status": "none", "timezone": None, "slots_proposed": []},
                },
            )
            if self._hubspot is not None:
                company_name = (
                    act2_context.enrichment_brief.firmographics.company_name
                    if act2_context is not None
                    else request.company_name
                )
                company_domain = (
                    act2_context.enrichment_brief.firmographics.domain
                    if act2_context is not None
                    else request.company_domain
                )
                await self._hubspot.append_event(
                    lead_id=request.lead_id,
                    event_type="reply_received",
                    payload={
                        "channel": request.channel,
                        "message_id": request.message_id,
                        "intent": intent,
                        "next_action": next_action,
                        "company_name": company_name,
                        "company_domain": company_domain,
                        "act2_brief_paths": act2_context.artifact_paths if act2_context is not None else {},
                    },
                    trace_id=trace_id,
                    idempotency_key=request.idempotency_key,
                )
                if act2_context is not None:
                    await self._hubspot.attach_brief_refs(
                        lead_id=request.lead_id,
                        brief_refs=[
                            act2_context.enrichment_brief.brief_id,
                            act2_context.compliance_brief.brief_id,
                            act2_context.news_brief.brief_id,
                        ],
                        trace_id=trace_id,
                        idempotency_key=f"{request.idempotency_key}:act2_brief_refs",
                    )
                await self._hubspot.set_stage(
                    lead_id=request.lead_id,
                    stage=next_state,
                    trace_id=trace_id,
                    idempotency_key=f"{request.idempotency_key}:stage",
                )
            log_processing_step(
                component="orchestration",
                step="handle_reply.done",
                message="Reply handling persisted session and optional HubSpot events",
                lead_id=request.lead_id,
                trace_id=trace_id,
                next_action=next_action,
            )
            reply_data: dict[str, Any] = {
                "lead_id": request.lead_id,
                "state": "reply_received",
                "next_action": next_action,
                "inbound_intent": intent,
            }
            if email_interp is not None:
                reply_data["suggested_reply_subject"] = email_interp.suggested_reply_subject
                reply_data["suggested_reply_body"] = email_interp.suggested_reply_body
                reply_data["llm_reply_confidence"] = email_interp.confidence
            env = ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data=reply_data,
            )
            self._state_repo.put_idempotency_response(
                idempotency_key=request.idempotency_key,
                response=env.model_dump(mode="json"),
            )
            return env
        except InvalidStateTransitionError as exc:
            log_processing_step(
                component="orchestration",
                step="handle_reply.error",
                message="Invalid transition during handle_reply",
                lead_id=request.lead_id,
                trace_id=trace_id,
                error=str(exc),
                level=logging.WARNING,
            )
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_STATE_TRANSITION",
                message=str(exc),
                retryable=False,
            )

    async def _run_act2_enrichment_before_reply(
        self,
        *,
        lead_id: str,
        request: LeadReplyRequest,
    ) -> Any | None:
        pipeline = self._enrichment_services.get("act2_pipeline")
        if pipeline is None:
            return None
        cached = self._state_repo.get_cached_enrichment(lead_id=lead_id)
        company_id = cached.get("company_id") if cached else None
        artifact = cached.get("artifact", {}) if cached else {}
        signals = artifact.get("signals", {}) if isinstance(artifact, dict) else {}
        crunchbase_summary = signals.get("crunchbase", {}).get("summary", {}) if isinstance(signals, dict) else {}
        company_name = request.company_name or crunchbase_summary.get("company_name")
        company_domain = request.company_domain or crunchbase_summary.get("domain")
        context = await pipeline.run_before_reply(
            lead_id=lead_id,
            company_id=company_id,
            company_name=company_name,
            company_domain=company_domain,
            from_email=request.from_email,
            from_number=request.from_number,
        )
        self._state_repo.upsert_act2_briefs(
            lead_id=lead_id,
            enrichment_brief=context.enrichment_brief.model_dump(mode="json"),
            compliance_brief=context.compliance_brief.model_dump(mode="json"),
            news_brief=context.news_brief.model_dump(mode="json"),
            artifact_paths=context.artifact_paths,
        )
        return context

    async def advance_state(self, request: LeadAdvanceRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_advance_{uuid4().hex[:12]}"
        log_processing_step(
            component="orchestration",
            step="advance_state.start",
            message="Advancing lead session stage",
            lead_id=request.lead_id,
            trace_id=trace_id,
            from_state=request.from_state,
            to_state=request.to_state,
            reason=request.reason,
            idempotency_key=request.idempotency_key,
        )
        session = self._state_repo.get_session_state(lead_id=request.lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{request.lead_id}'.",
                retryable=False,
            )
        cached = self._state_repo.get_idempotency_response(idempotency_key=request.idempotency_key)
        if cached is not None:
            return ResponseEnvelope.model_validate(cached)
        try:
            if session["current_stage"] != request.from_state:
                raise InvalidStateTransitionError(from_state=session["current_stage"], to_state=request.to_state)
            validate_lead_transition(from_state=request.from_state, to_state=request.to_state)
            if (request.from_state, request.to_state) == ("in_review", "queued_to_send"):
                send_err = await self._send_approved_outreach_if_configured(request=request, trace_id=trace_id)
                if send_err:
                    return self._failure(
                        request_id=request_id,
                        trace_id=trace_id,
                        code="ORCHESTRATION_FAILED",
                        message=send_err,
                        retryable=False,
                    )
            if (request.from_state, request.to_state) == ("drafting", "in_review"):
                await self._review_outreach_on_advance(
                    lead_id=request.lead_id,
                    trace_id=trace_id,
                    idempotency_key=request.idempotency_key,
                )
            if (request.from_state, request.to_state) == ("brief_ready", "drafting"):
                await self._materialize_outreach_draft(request=request, trace_id=trace_id)
            self._state_repo.upsert_session_state(
                lead_id=request.lead_id,
                payload={
                    **session,
                    "current_stage": request.to_state,
                    "next_best_action": "none",
                    "current_objective": request.reason,
                },
            )
            if self._hubspot is not None:
                await self._hubspot.set_stage(
                    lead_id=request.lead_id,
                    stage=request.to_state,
                    trace_id=trace_id,
                    idempotency_key=request.idempotency_key,
                )
            log_processing_step(
                component="orchestration",
                step="advance_state.done",
                message="Lead stage advanced",
                lead_id=request.lead_id,
                trace_id=trace_id,
                current_state=request.to_state,
            )
            env = ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="success",
                data={"lead_id": request.lead_id, "current_state": request.to_state},
            )
            self._state_repo.put_idempotency_response(
                idempotency_key=request.idempotency_key,
                response=env.model_dump(mode="json"),
            )
            return env
        except InvalidStateTransitionError as exc:
            log_processing_step(
                component="orchestration",
                step="advance_state.error",
                message="advance_state rejected",
                lead_id=request.lead_id,
                trace_id=trace_id,
                error=str(exc),
                level=logging.WARNING,
            )
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_STATE_TRANSITION",
                message=str(exc),
                retryable=False,
            )

    def _recent_outbound_email_snippet(self, *, lead_id: str) -> str | None:
        rows = self._state_repo.list_messages(lead_id=lead_id, limit=16)
        for row in rows:
            if row.get("channel") == "email" and row.get("direction") == "outbound":
                meta = row.get("metadata") or {}
                subject = str(meta.get("subject") or "") if isinstance(meta, dict) else ""
                body = str(row.get("content") or "")
                return f"Subject: {subject}\n\n{body[:4000]}"
        return None

    def _outreach_flow_deps(self) -> OutreachFlowDeps:
        return OutreachFlowDeps(
            settings=self._settings,
            state_repo=self._state_repo,
            llm=self._enrichment_services.get("llm"),
            policy=self._policy,
        )

    async def outreach_draft(self, request: OutreachDraftRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_outreach_draft_{uuid4().hex[:12]}"
        idem = request.idempotency_key or f"outreach_draft:{request.lead_id}:{uuid4().hex[:12]}"
        if self._state_repo.get_session_state(lead_id=request.lead_id) is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{request.lead_id}'.",
                retryable=False,
            )
        try:
            to_email = (
                (request.to_email or "").strip()
                or self._settings.default_outreach_to_email.strip()
                or "draft-only@invalid.local"
            )
            company_name = self._company_display_name(request.lead_id, fallback=request.lead_id)
            od = await run_outreach_draft_only(
                self._outreach_flow_deps(),
                lead_id=request.lead_id,
                trace_id=trace_id,
                idempotency_key=idem,
                to_email=to_email,
                company_name=company_name,
                variant=request.variant,
                brief_id=request.brief_id,
                gap_brief_id=request.gap_brief_id,
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="success",
                data={"draft_id": od.draft_id, "subject": od.subject, "body": od.text_body or ""},
            )
        except Exception as exc:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="ORCHESTRATION_FAILED",
                message=str(exc),
                retryable=False,
            )

    async def outreach_review(self, request: OutreachReviewRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_outreach_review_{uuid4().hex[:12]}"
        try:
            rec = await run_outreach_review_for_lead(
                self._outreach_flow_deps(),
                lead_id=request.lead_id,
                draft_id=request.draft_id,
                trace_id=trace_id,
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="success",
                data={
                    "review_id": rec["review_id"],
                    "status": rec["status"],
                    "final_send_ok": rec["final_send_ok"],
                },
            )
        except ValueError as exc:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=str(exc),
                retryable=False,
            )
        except Exception as exc:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="ORCHESTRATION_FAILED",
                message=str(exc),
                retryable=False,
            )

    async def outreach_send(self, request: OutreachSendRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_outreach_send_{uuid4().hex[:12]}"
        idem = request.idempotency_key or f"outreach_send:{request.lead_id}:{uuid4().hex[:12]}"
        mid, err = await run_outreach_send_for_lead(
            self._outreach_flow_deps(),
            lead_id=request.lead_id,
            draft_id=request.draft_id,
            review_id=request.review_id,
            trace_id=trace_id,
            idempotency_key=idem,
            to_email=request.to_email,
            email_service=self._email_service,
        )
        if err:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="ORCHESTRATION_FAILED",
                message=err,
                retryable=False,
            )
        delivery = "queued" if mid and mid != "skipped_no_email_service" else "skipped_no_provider"
        msg_id = None if mid == "skipped_no_email_service" else mid
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"message_id": msg_id, "delivery_status": delivery},
        )

    async def memory_session_write(self, request: MemorySessionWriteRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_mem_write_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=request.lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{request.lead_id}'.",
                retryable=False,
            )
        allowed = {
            "next_best_action",
            "current_objective",
            "pending_actions",
            "policy_flags",
            "kb_refs",
            "brief_refs",
        }
        patch = {k: v for k, v in request.session_state.items() if k in allowed}
        self._state_repo.upsert_session_state(lead_id=request.lead_id, payload={**session, **patch})
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"lead_id": request.lead_id, "updated_keys": list(patch.keys())},
        )

    def memory_session_get(self, *, lead_id: str) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_mem_get_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{lead_id}'.",
                retryable=False,
            )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"lead_id": lead_id, "session_state": session},
        )

    def memory_evidence_list(self, *, lead_id: str, limit: int = 200) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_mem_ev_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{lead_id}'.",
                retryable=False,
            )
        edges = self._state_repo.list_evidence_edges(lead_id=lead_id, limit=limit)
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"lead_id": lead_id, "edges": edges},
        )

    def list_pipelines(self, *, limit: int = 200) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_pipelines_{uuid4().hex[:12]}"
        rows = self._state_repo.list_pipeline_runs(limit=limit)
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"pipelines": rows},
        )

    def get_pipeline(self, *, lead_id: str) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_pipeline_get_{uuid4().hex[:12]}"
        row = self._state_repo.get_pipeline_run(lead_id=lead_id)
        if row is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{lead_id}'.",
                retryable=False,
            )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"pipeline": row},
        )

    def delete_pipeline(self, *, lead_id: str) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_pipeline_del_{uuid4().hex[:12]}"
        deleted = self._state_repo.delete_pipeline_run(lead_id=lead_id)
        if not deleted:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{lead_id}'.",
                retryable=False,
            )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"lead_id": lead_id, "deleted": True},
        )

    def get_state(self, *, lead_id: str) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_state_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{lead_id}'.",
                retryable=False,
            )
        briefs = self._state_repo.get_briefs(lead_id=lead_id) or {}
        ai_block = briefs.get("ai_maturity_score", {})
        classification = briefs.get("hiring_signal_brief", {})
        pipeline = self._state_repo.get_pipeline_run(lead_id=lead_id) or {}
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={
                "lead_id": lead_id,
                "state": session["current_stage"],
                "segment": classification.get("primary_segment_hypothesis"),
                "segment_confidence": classification.get("segment_confidence", 0.0),
                "ai_maturity_score": ai_block.get("score"),
                "pending_actions": session.get("pending_actions", []),
                "kb_refs": session.get("kb_refs", []),
                "policy_flags": session.get("policy_flags", []),
                "updated_at": session.get("updated_at"),
                "company_id": pipeline.get("company_id"),
                "company_name": pipeline.get("company_name"),
                "company_domain": pipeline.get("company_domain"),
            },
        )

    def get_lead_briefs(self, *, lead_id: str) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_briefs_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{lead_id}'.",
                retryable=False,
            )
        briefs = self._state_repo.get_briefs(lead_id=lead_id) or {}
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"lead_id": lead_id, "briefs": briefs},
        )

    async def compact_context(self, request: LeadCompactRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_compact_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=request.lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{request.lead_id}'.",
                retryable=False,
            )
        compaction_ref = f"compact_{uuid4().hex[:10]}"
        log_trace_event(
            event_type="memory_compaction",
            trace_id=trace_id,
            lead_id=request.lead_id,
            status="ok",
            payload={
                "compaction_ref": compaction_ref,
                "reason": request.reason,
                "preserved_brief_refs": session.get("brief_refs", []),
                "preserved_pending_actions": session.get("pending_actions", []),
            },
        )
        self._state_repo.upsert_session_state(
            lead_id=request.lead_id,
            payload={
                **session,
                "kb_refs": [*session.get("kb_refs", []), compaction_ref],
                "current_objective": request.reason,
            },
        )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={
                "lead_id": request.lead_id,
                "compaction_ref": compaction_ref,
                "current_state": session["current_stage"],
            },
        )

    async def rehydrate_context(self, request: LeadRehydrateRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_rehydrate_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=request.lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{request.lead_id}'.",
                retryable=False,
            )
        ref = f"rehydrated_{uuid4().hex[:10]}"
        log_trace_event(
            event_type="memory_rehydrate",
            trace_id=trace_id,
            lead_id=request.lead_id,
            status="ok",
            payload={
                "rehydrated_state_ref": ref,
                "current_stage": session["current_stage"],
                "brief_refs": session.get("brief_refs", []),
            },
        )
        log_processing_step(
            component="orchestration",
            step="rehydrate",
            message="Rehydration marker recorded (context_compaction.md minimal working set)",
            lead_id=request.lead_id,
            trace_id=trace_id,
            ref=ref,
        )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={
                "lead_id": request.lead_id,
                "rehydrated_state_ref": ref,
                "current_state": session["current_stage"],
            },
        )

    def _company_display_name(self, lead_id: str, fallback: str = "") -> str:
        cached = self._state_repo.get_cached_enrichment(lead_id=lead_id)
        if not cached:
            return fallback or lead_id
        art = cached.get("artifact") or {}
        if not isinstance(art, dict):
            return fallback or lead_id
        sig = art.get("signals", {}).get("crunchbase", {}).get("summary", {}) or {}
        return str(sig.get("company_name") or fallback or lead_id)

    async def _materialize_outreach_draft(self, *, request: LeadAdvanceRequest, trace_id: str) -> None:
        to_email = (request.outreach_to_email or "").strip() or self._settings.default_outreach_to_email.strip()
        if not to_email:
            to_email = "draft-only@invalid.local"
        company_name = self._company_display_name(request.lead_id, fallback=request.lead_id)
        await run_outreach_draft_only(
            self._outreach_flow_deps(),
            lead_id=request.lead_id,
            trace_id=trace_id,
            idempotency_key=request.idempotency_key,
            to_email=to_email,
            company_name=company_name,
            variant="cold_email",
            brief_id=None,
            gap_brief_id=None,
        )

    async def _review_outreach_on_advance(
        self, *, lead_id: str, trace_id: str, idempotency_key: str
    ) -> None:
        del idempotency_key
        row = self._state_repo.get_outreach_draft(lead_id=lead_id)
        if row is None:
            raise RuntimeError("outreach_missing_draft")
        raw = row["draft"]
        outbound_d, existing = parse_outreach_stored(raw)
        if existing is not None:
            return
        draft_id = outbound_d.get("draft_id")
        if not draft_id:
            raise RuntimeError("outreach_invalid_draft")
        await run_outreach_review_for_lead(
            self._outreach_flow_deps(),
            lead_id=lead_id,
            draft_id=str(draft_id),
            trace_id=trace_id,
        )

    async def _send_approved_outreach_if_configured(
        self, *, request: LeadAdvanceRequest, trace_id: str
    ) -> str | None:
        row = self._state_repo.get_outreach_draft(lead_id=request.lead_id)
        if row is None:
            return "No outreach draft found; advance through drafting first."
        raw_blob = row["draft"]
        outbound_d, review = parse_outreach_stored(raw_blob)
        if review is None:
            return "Outreach has not been reviewed; complete review before send."
        if not review.get("final_send_ok"):
            return "Review final_send_ok is false; cannot send."
        outbound = OutboundEmailRequest.model_validate(outbound_d)
        rs = outbound.review_status
        if rs not in ("approved", "approved_with_edits"):
            return f"Outreach review_status '{rs}' is not send-eligible."
        if row.get("last_send_idempotency") == request.idempotency_key:
            return None
        if self._email_service is None:
            log_processing_step(
                component="orchestration",
                step="advance.send.skip",
                message="EmailService not configured; skipping physical send",
                lead_id=request.lead_id,
                trace_id=trace_id,
            )
            return None
        to_email = (request.outreach_to_email or "").strip() or self._settings.default_outreach_to_email.strip()
        if not to_email or "@" not in to_email or to_email.endswith("invalid.local"):
            return "Provide outreach_to_email or configure DEFAULT_OUTREACH_TO_EMAIL for first send."
        merged = {
            **outbound.model_dump(mode="json"),
            "to_email": to_email,
            "trace_id": trace_id,
            "idempotency_key": request.idempotency_key,
        }
        req = OutboundEmailRequest.model_validate(merged)
        res = await self._email_service.send_email(req)
        if not res.accepted:
            return res.error.error_message if res.error else "send_failed"
        self._state_repo.mark_outreach_sent_idempotency(
            lead_id=request.lead_id, idempotency_key=request.idempotency_key
        )
        meta = req.metadata or {}
        self._state_repo.append_message(
            lead_id=request.lead_id,
            channel="email",
            message_id=f"outreach_sent_{uuid4().hex[:12]}",
            direction="outbound",
            content=req.text_body or "",
            metadata={
                "subject": req.subject,
                "kind": "first_touch_sent",
                "resend_message_id": res.provider_message_id,
                "draft_id": req.draft_id,
                "email_thread_id": meta.get("email_thread_id"),
            },
        )
        return None

    async def escalate(self, request: LeadEscalationRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_escalate_{uuid4().hex[:12]}"
        log_processing_step(
            component="orchestration",
            step="escalate",
            message="Escalating lead to human handoff",
            lead_id=request.lead_id,
            trace_id=trace_id,
            reason_code=request.reason_code,
        )
        cached = self._state_repo.get_idempotency_response(idempotency_key=request.idempotency_key)
        if cached is not None:
            return ResponseEnvelope.model_validate(cached)
        session = self._state_repo.get_session_state(lead_id=request.lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{request.lead_id}'.",
                retryable=False,
            )
        self._state_repo.upsert_session_state(
            lead_id=request.lead_id,
            payload={
                **session,
                "current_stage": "handoff_required",
                "next_best_action": "escalate",
                "current_objective": "human_handoff",
                "handoff_required": True,
                "policy_flags": list(set([*session.get("policy_flags", []), request.reason_code])),
            },
        )
        if self._hubspot is not None:
            await self._hubspot.append_event(
                lead_id=request.lead_id,
                event_type="handoff_triggered",
                payload={
                    "reason_code": request.reason_code,
                    "summary": request.summary,
                    "evidence_refs": request.evidence_refs,
                },
                trace_id=trace_id,
                idempotency_key=request.idempotency_key,
            )
            await self._hubspot.set_stage(
                lead_id=request.lead_id,
                stage="handoff_required",
                trace_id=trace_id,
                idempotency_key=f"{request.idempotency_key}:stage",
            )
        env = ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"lead_id": request.lead_id, "state": "handoff_required", "handoff_id": f"handoff_{uuid4().hex[:10]}"},
        )
        self._state_repo.put_idempotency_response(
            idempotency_key=request.idempotency_key,
            response=env.model_dump(mode="json"),
        )
        return env

    @staticmethod
    def _lead_id_for_company(*, company_id: str) -> str:
        digest = hashlib.sha256(company_id.encode("utf-8")).hexdigest()[:10]
        return f"lead_{digest}"

    @staticmethod
    def _failure(
        *,
        request_id: str,
        trace_id: str,
        code: str,
        message: str,
        retryable: bool,
    ) -> ResponseEnvelope:
        log_processing_step(
            component="orchestration",
            step="response.failure",
            message="Returning failure response envelope",
            trace_id=trace_id,
            error_code=code,
            error_message=message,
            retryable=retryable,
            level=logging.WARNING,
        )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="failure",
            data={},
            error=ErrorEnvelope(error_code=code, error_message=message, retryable=retryable),
            timestamp=datetime.now(UTC),
        )
