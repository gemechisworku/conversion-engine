"""Runtime orchestration handlers aligned to orchestration API contracts."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from dateutil import parser as date_parser
from dateutil import tz as date_tz

from agent.config.settings import Settings
from agent.graphs.lead_intake_langgraph import LeadIntakeGraphDeps, compile_lead_intake_graph
from agent.graphs.reply_langgraph import ReplyRouteGraphDeps, compile_reply_route_graph
from agent.graphs.state import LeadGraphState
from agent.graphs.transitions import InvalidStateTransitionError, validate_lead_transition
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.calendar.calcom_client import CalComService, book_and_sync_crm
from agent.services.calendar.schemas import BookingRequest
from agent.services.common.schemas import ErrorEnvelope
from agent.services.crm.schemas import CRMWriteResult
from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.conversation.email_llm import (
    InboundEmailInterpretLLM,
    interpret_inbound_email_and_draft_reply,
)
from agent.services.email.client import EmailService
from agent.services.email.reply_address import build_lead_reply_address, extract_lead_id_from_reply_address
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
    LeadScheduleBookRequest,
    LeadSchedulePrepareRequest,
    LeadRehydrateRequest,
    LeadRespondRequest,
    LeadReplyRequest,
    MemorySessionWriteRequest,
    OutreachDraftRequest,
    OutreachReviewRequest,
    OutreachSendRequest,
    ResponseEnvelope,
)
from agent.services.outreach.outreach_flow import OutreachFlowDeps, run_outreach_draft_only, run_outreach_review_for_lead, run_outreach_send_for_lead
from agent.services.outreach.outreach_payload import parse_outreach_stored
from agent.services.policy.channel_handoff import append_scheduling_cta, decide_channel_handoff
from agent.services.policy.channel_policy import LeadChannelState
from agent.services.policy.outbound_policy import OutboundPolicyService
from agent.services.sms.client import SMSService
from agent.services.sms.schemas import OutboundSMSRequest

WEBHOOK_LOGGER = logging.getLogger("agent.webhooks.resend")


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
        calcom_service: CalComService | None = None,
        email_service: EmailService | None = None,
        sms_service: SMSService | None = None,
    ) -> None:
        self._settings = settings
        self._state_repo = state_repo
        self._enrichment_services = enrichment_services
        self._hubspot = hubspot_service
        self._calcom = calcom_service
        self._email_service = email_service
        self._sms_service = sms_service
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
                    "from_email": request.from_email,
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
            transcript_for_route = self._conversation_transcript_for_reply_routing(lead_id=request.lead_id)
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
                        "conversation_transcript": transcript_for_route or None,
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
            meeting_time_hint = self._meeting_time_from_reply_context(
                email_interp=email_interp,
                inbound_content=request.content,
                transcript=transcript_for_route,
            )
            if request.channel.lower() == "email":
                suggested_subject: str | None = None
                suggested_body: str | None = None
                suggested_confidence: float | None = None
                if email_interp is not None and next_action != "schedule":
                    suggested_subject = email_interp.suggested_reply_subject
                    suggested_body = email_interp.suggested_reply_body
                    suggested_confidence = email_interp.confidence
                elif next_action != "schedule":
                    suggested_subject, suggested_body = self._fallback_suggested_reply_for_action(
                        lead_id=request.lead_id,
                        next_action=next_action,
                        inbound_subject=request.subject,
                        inbound_content=request.content,
                    )
                in_reply_to_hdr, refs_hdr = self._state_repo.get_email_thread_reply_headers(
                    lead_id=request.lead_id
                )
                reply_target = normalize_message_id(request.rfc_message_id) or normalize_message_id(
                    in_reply_to_hdr
                )
                refs_combined = merge_references_header(refs_hdr, reply_target)
                thread_id = self._state_repo.ensure_email_thread(lead_id=request.lead_id)
                if suggested_body:
                    self._state_repo.append_message(
                        lead_id=request.lead_id,
                        channel="email",
                        message_id=f"suggested_email_reply_{uuid4().hex[:12]}",
                        direction="outbound",
                        content=suggested_body,
                        metadata={
                            "kind": "suggested_reply_email",
                            "subject": suggested_subject or "Re: Follow-up",
                            "reply_to_message_id": request.message_id,
                            "intent": intent,
                            "source_next_action": next_action,
                            "llm_confidence": suggested_confidence,
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

            prev_conv = self._state_repo.get_conversation_state(lead_id=request.lead_id) or {}
            prev_raw = prev_conv.get("scheduling_context")
            prev_sched: dict[str, Any] = (
                prev_raw
                if isinstance(prev_raw, dict)
                else {"booking_status": "none", "timezone": None, "slots_proposed": []}
            )
            slot_text: str | None = meeting_time_hint
            if slot_text:
                slots_out: list[Any] = [
                    {
                        "source": (
                            "llm_thread_extraction"
                            if email_interp is not None and bool(email_interp.meeting_time_from_thread)
                            else "heuristic_thread_extraction"
                        ),
                        "text": slot_text,
                        "inbound_message_id": request.message_id,
                    }
                ]
            else:
                prev_slots = prev_sched.get("slots_proposed")
                slots_out = list(prev_slots) if isinstance(prev_slots, list) else []
            scheduling_ctx = dict(prev_sched)
            scheduling_ctx.setdefault("booking_status", "none")
            scheduling_ctx["slots_proposed"] = slots_out
            if slot_text:
                scheduling_ctx["last_extracted_inbound_message_id"] = request.message_id
                scheduling_ctx["requested_time_text"] = slot_text
            scheduling_ctx.setdefault("requested_time_text", None)

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
                    "scheduling_context": scheduling_ctx,
                },
            )
            self._state_repo.update_pipeline_run_stage(
                lead_id=request.lead_id,
                stage=next_state,
                trace_id=trace_id,
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
            if email_interp is not None and next_action != "schedule":
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

    def _fallback_suggested_reply_for_action(
        self,
        *,
        lead_id: str,
        next_action: str,
        inbound_subject: str | None,
        inbound_content: str,
    ) -> tuple[str, str]:
        company_name = self._company_display_name(lead_id, fallback="there")
        subject_hint = (inbound_subject or "").strip()
        if subject_hint and subject_hint.lower().startswith("re:"):
            subject = subject_hint
        elif subject_hint:
            subject = f"Re: {subject_hint}"
        else:
            subject = "Re: Thanks for your reply"
        body_map: dict[str, str] = {
            "schedule": (
                f"Thanks for the reply.\n\nHappy to share more about how we work with teams like {company_name}. "
                "I can align on your preferred window and send a calendar confirmation."
            ),
            "qualify": (
                "Thanks for the thoughtful question.\n\nIn short, we provide dedicated data/ML engineering capacity "
                "for delivery bottlenecks without forcing immediate permanent hiring. "
                "If helpful, I can send a concise 3-point breakdown tailored to your current priorities."
            ),
            "clarify": (
                "Thanks for the question.\n\nWe typically support with: "
                "1) scoped data/ML delivery support, "
                "2) fast onboarding to existing workflows, and "
                "3) clear weekly progress cadence. "
                "If you share your top objective, I can tailor this further."
            ),
            "handle_objection": (
                "Completely fair concern.\n\nIf useful, we can start with a small, low-risk scope so you can evaluate fit "
                "before any larger commitment. I can outline what that would look like in your context."
            ),
            "nurture": (
                "Thanks for the candid response.\n\nNo pressure on timing. "
                "I can send a brief note with practical examples and you can revisit when priorities align."
            ),
            "escalate": (
                "Thanks for sharing that.\n\nI want to route this to the right human owner to provide the most accurate response. "
                "I will follow up shortly with a concrete next step."
            ),
        }
        default_body = (
            "Thanks for the reply.\n\nI can share a short, tailored overview of how we can help based on your priorities. "
            "If you share your main goal, I will keep it concise."
        )
        _ = inbound_content
        return subject, body_map.get(next_action, default_body)

    @staticmethod
    def _meeting_text_from_scheduling_context(scheduling_context: dict[str, Any]) -> str | None:
        requested = scheduling_context.get("requested_time_text")
        if isinstance(requested, str) and requested.strip():
            return requested.strip()
        slots = scheduling_context.get("slots_proposed")
        if isinstance(slots, list):
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                text = slot.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return None

    def _meeting_time_from_reply_context(
        self,
        *,
        email_interp: InboundEmailInterpretLLM | None,
        inbound_content: str,
        transcript: str,
    ) -> str | None:
        inbound_hint = self._extract_schedule_phrase_from_text(inbound_content)
        if inbound_hint:
            return inbound_hint
        inbound_transcript = self._inbound_only_transcript(transcript)
        transcript_hint = self._extract_schedule_phrase_from_text(inbound_transcript)
        if transcript_hint:
            return transcript_hint
        if email_interp is not None and email_interp.meeting_time_from_thread:
            text = email_interp.meeting_time_from_thread.strip()
            if text and not self._looks_like_outbound_question(text):
                return text
        return None

    @staticmethod
    def _extract_schedule_phrase_from_text(text: str) -> str | None:
        if not text:
            return None
        lines = [segment.strip() for segment in re.split(r"[\r\n]+", text) if segment.strip()]
        schedule_keywords = (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "today",
            "tomorrow",
            "next ",
            " am",
            " pm",
            "a.m",
            "p.m",
            "timezone",
            "utc",
            "gmt",
            "eat",
            "est",
            "pst",
            "cst",
            "mst",
            "cet",
        )
        preference_keywords = ("works", "available", "free", "can do", "would work", "prefer")
        candidates: list[str] = []
        for line in lines:
            lowered = line.lower()
            if any(token in lowered for token in schedule_keywords):
                candidates.append(line)
        if not candidates:
            return None
        for line in candidates:
            lowered = line.lower()
            if any(token in lowered for token in preference_keywords):
                return line[:500]
        return candidates[0][:500]

    async def _extract_meeting_time_with_optional_llm(
        self,
        *,
        lead_id: str,
        trace_id: str,
        inbound_subject: str,
        inbound_body: str,
        transcript: str,
    ) -> str | None:
        inbound_hint = self._extract_schedule_phrase_from_text(inbound_body)
        if inbound_hint:
            return inbound_hint
        inbound_transcript = self._inbound_only_transcript(transcript)
        transcript_hint = self._extract_schedule_phrase_from_text(inbound_transcript)
        if transcript_hint:
            return transcript_hint
        llm = self._enrichment_services.get("llm")
        if llm is not None and getattr(llm, "configured", False):
            briefs_all = self._state_repo.get_briefs(lead_id=lead_id) or {}
            hiring = briefs_all.get("hiring_signal_brief")
            hiring_dict = hiring if isinstance(hiring, dict) else {}
            email_interp = await interpret_inbound_email_and_draft_reply(
                settings=self._settings,
                llm=llm,
                company_name=self._company_display_name(lead_id, fallback=lead_id),
                inbound_subject=inbound_subject or "(no subject)",
                inbound_body=inbound_body or "(no body)",
                recent_outbound_context=self._recent_outbound_email_snippet(lead_id=lead_id),
                conversation_transcript=transcript,
                hiring_signal_brief=hiring_dict,
                trace_id=trace_id,
                lead_id=lead_id,
            )
            if email_interp is not None and email_interp.meeting_time_from_thread:
                value = email_interp.meeting_time_from_thread.strip()
                if value and not self._looks_like_outbound_question(value):
                    return value
        return None

    @staticmethod
    def _inbound_only_transcript(transcript: str) -> str:
        if not transcript:
            return ""
        pattern = re.compile(
            r"\[[^\]]+\]\s+inbound\s+\w+:\n(.*?)(?=\n\n---\n\n\[[^\]]+\]\s+\w+\s+\w+:\n|\Z)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        chunks = [match.group(1).strip() for match in pattern.finditer(transcript) if match.group(1).strip()]
        return "\n\n".join(chunks)

    @staticmethod
    def _looks_like_outbound_question(text: str) -> bool:
        lowered = text.lower()
        if "?" not in lowered:
            return False
        question_markers = (
            "would ",
            "could ",
            "can you ",
            "if yes",
            "share your timezone",
            "open to",
        )
        return any(marker in lowered for marker in question_markers)

    @staticmethod
    def _resolve_tz_name_from_text(text: str | None) -> str | None:
        if not text:
            return None
        lowered = text.lower()
        tz_map = {
            "eat": "Africa/Addis_Ababa",
            "eat)": "Africa/Addis_Ababa",
            "eest": "Europe/Helsinki",
            "cet": "Europe/Berlin",
            "cest": "Europe/Berlin",
            "est": "America/New_York",
            "edt": "America/New_York",
            "cst": "America/Chicago",
            "cdt": "America/Chicago",
            "mst": "America/Denver",
            "mdt": "America/Denver",
            "pst": "America/Los_Angeles",
            "pdt": "America/Los_Angeles",
            "gmt": "Etc/GMT",
            "utc": "UTC",
        }
        for token, tz_name in tz_map.items():
            if f" {token}" in lowered or lowered.startswith(token):
                return tz_name
        return None

    def _resolve_meeting_start_from_text(
        self,
        *,
        meeting_text: str,
        timezone_hint: str | None,
    ) -> tuple[datetime | None, str | None]:
        if not meeting_text.strip():
            return None, timezone_hint
        tz_name = timezone_hint or self._resolve_tz_name_from_text(meeting_text)
        tzinfo = date_tz.gettz(tz_name) if tz_name else None
        now = datetime.now(tz=tzinfo or UTC)
        default_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)
        try:
            parsed = date_parser.parse(
                meeting_text,
                fuzzy=True,
                default=default_dt,
                tzinfos={
                    "EAT": date_tz.gettz("Africa/Addis_Ababa"),
                    "UTC": date_tz.gettz("UTC"),
                    "GMT": date_tz.gettz("Etc/GMT"),
                    "EST": date_tz.gettz("America/New_York"),
                    "EDT": date_tz.gettz("America/New_York"),
                    "CST": date_tz.gettz("America/Chicago"),
                    "PST": date_tz.gettz("America/Los_Angeles"),
                },
            )
        except (ValueError, OverflowError):
            return None, tz_name
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tzinfo or UTC)
        if parsed < now - timedelta(minutes=5):
            parsed = parsed + timedelta(days=7)
        return parsed, (tz_name or (parsed.tzname() if parsed.tzinfo is not None else None))

    def _resolve_scheduling_portal_url(
        self,
        *,
        lead_id: str,
        meeting_text: str | None,
        starts_at: datetime | None,
        prospect_email: str | None,
    ) -> str | None:
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        base = self._settings.calcom_booking_portal_url.strip()
        if not base:
            username = self._settings.calcom_username.strip()
            slug = self._settings.calcom_event_type_slug.strip()
            if username and slug:
                base = f"https://cal.com/{username}/{slug}"
            elif username:
                base = f"https://cal.com/{username}"
            else:
                base = "https://cal.com"
        parsed = urlparse(base)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if prospect_email:
            query.setdefault("email", prospect_email)
        if starts_at is not None:
            query.setdefault("date", starts_at.date().isoformat())
        if meeting_text:
            query.setdefault("notes", meeting_text[:180])
        query.setdefault("utm_source", "tenacious_ops")
        query.setdefault("lead_id", lead_id)
        return urlunparse(parsed._replace(query=urlencode(query)))

    @staticmethod
    def _prospect_name_from_latest_inbound(inbound_payload: dict[str, Any]) -> str | None:
        from_email = str(inbound_payload.get("from_email") or "").strip()
        if not from_email or "@" not in from_email:
            return None
        local = from_email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
        if not local:
            return None
        return " ".join(part.capitalize() for part in local.split() if part)

    def _channel_state_for_lead(self, *, lead_id: str) -> LeadChannelState:
        rows = self._state_repo.list_messages(lead_id=lead_id, limit=200)
        has_prior_email_reply = any(
            row.get("direction") == "inbound" and str(row.get("channel") or "").lower() == "email"
            for row in rows
        )
        has_recent_inbound_sms = any(
            row.get("direction") == "inbound" and str(row.get("channel") or "").lower() == "sms"
            for row in rows
        )
        conversation = self._state_repo.get_conversation_state(lead_id=lead_id) or {}
        explicit_warm_status = bool(
            conversation.get("last_customer_intent") in {"interest", "schedule"}
            or has_prior_email_reply
            or has_recent_inbound_sms
        )
        return LeadChannelState(
            lead_id=lead_id,
            has_prior_email_reply=has_prior_email_reply,
            explicit_warm_status=explicit_warm_status,
            has_recent_inbound_sms=has_recent_inbound_sms,
        )

    def _latest_inbound_sms_number(self, *, lead_id: str) -> str | None:
        rows = self._state_repo.list_messages(lead_id=lead_id, limit=200)
        for row in rows:
            if row.get("direction") != "inbound" or str(row.get("channel") or "").lower() != "sms":
                continue
            metadata = row.get("metadata")
            if isinstance(metadata, dict):
                from_number = str(metadata.get("from_number") or "").strip()
                if from_number:
                    return from_number
        return self._state_repo.get_bound_phone_for_lead(lead_id=lead_id)

    def _should_include_scheduling_link(
        self,
        *,
        session: dict[str, Any],
        conversation: dict[str, Any],
    ) -> bool:
        next_action = str(session.get("next_best_action") or "").strip().lower()
        if next_action in {"schedule", "delegate_scheduler"}:
            return True
        last_intent = str(conversation.get("last_customer_intent") or "").strip().lower()
        return last_intent == "schedule"

    async def _append_hubspot_channel_handoff_event(
        self,
        *,
        lead_id: str,
        trace_id: str,
        requested_channel: str,
        resolved_channel: str,
        reason: str,
        idempotency_key: str,
    ) -> None:
        if self._hubspot is None:
            return
        await self._hubspot.append_event(
            lead_id=lead_id,
            event_type="channel_handoff",
            payload={
                "requested_channel": requested_channel,
                "resolved_channel": resolved_channel,
                "reason": reason,
            },
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )

    async def _append_hubspot_scheduling_link_event(
        self,
        *,
        lead_id: str,
        trace_id: str,
        channel: str,
        scheduling_portal_url: str,
        idempotency_key: str,
    ) -> None:
        if self._hubspot is None:
            return
        await self._hubspot.append_event(
            lead_id=lead_id,
            event_type="scheduling_link_shared",
            payload={"channel": channel, "scheduling_portal_url": scheduling_portal_url},
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )

    async def respond_to_lead(self, request: LeadRespondRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_respond_{uuid4().hex[:12]}"
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
        channel = request.channel.strip().lower()
        if channel not in {"email", "sms"}:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unsupported channel '{request.channel}'.",
                retryable=False,
            )
        content = request.content.strip()
        if not content:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message="Outbound reply content is required.",
                retryable=False,
            )
        conversation = self._state_repo.get_conversation_state(lead_id=request.lead_id) or {}
        lead_channel_state = self._channel_state_for_lead(lead_id=request.lead_id)
        handoff = decide_channel_handoff(
            lead_id=request.lead_id,
            requested_channel=channel,
            lead_state=lead_channel_state,
            trace_id=trace_id,
        )
        if not handoff.allowed:
            await self._append_hubspot_channel_handoff_event(
                lead_id=request.lead_id,
                trace_id=trace_id,
                requested_channel=channel,
                resolved_channel=handoff.resolved_channel,
                reason=handoff.reason,
                idempotency_key=f"{request.idempotency_key}:handoff_blocked",
            )
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="POLICY_BLOCKED",
                message=handoff.reason,
                retryable=False,
            )
        scheduling_portal_url: str | None = None
        outbound_channel = handoff.resolved_channel
        sent_message_id: str
        if outbound_channel == "email":
            if self._email_service is None:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="CONFIG_ERROR",
                    message="EmailService not configured.",
                    retryable=False,
                )
            to_email = (request.to_email or "").strip()
            if not to_email:
                latest_inbound = self._state_repo.get_latest_inbound_email_for_lead(lead_id=request.lead_id) or {}
                to_email = str(latest_inbound.get("from_email") or "").strip()
                if not to_email:
                    rows = self._state_repo.list_messages(lead_id=request.lead_id, limit=100)
                    for row in rows:
                        if row.get("direction") == "inbound" and row.get("channel") == "email":
                            meta = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
                            candidate = str(meta.get("from_email") or "").strip()
                            if candidate:
                                to_email = candidate
                                break
            if not to_email or "@" not in to_email:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="INVALID_INPUT",
                    message="Recipient email could not be resolved. Provide to_email explicitly.",
                    retryable=False,
                )
            latest_inbound = self._state_repo.get_latest_inbound_email_for_lead(lead_id=request.lead_id) or {}
            inbound_subject = str(latest_inbound.get("subject") or "").strip()
            subject = (request.subject or "").strip()
            if not subject:
                if inbound_subject.lower().startswith("re:"):
                    subject = inbound_subject
                elif inbound_subject:
                    subject = f"Re: {inbound_subject}"
                else:
                    subject = "Re: Follow-up"
            outbound_content = content
            if self._should_include_scheduling_link(session=session, conversation=conversation):
                scheduling_portal_url = self._resolve_scheduling_portal_url(
                    lead_id=request.lead_id,
                    meeting_text=None,
                    starts_at=None,
                    prospect_email=to_email,
                )
                outbound_content = append_scheduling_cta(
                    content=outbound_content,
                    channel="email",
                    scheduling_portal_url=scheduling_portal_url,
                )
            in_reply_to, references = self._state_repo.get_email_thread_reply_headers(lead_id=request.lead_id)
            outbound = OutboundEmailRequest(
                lead_id=request.lead_id,
                draft_id=f"reply_draft_{uuid4().hex[:12]}",
                review_id=f"ui_reply_review_{uuid4().hex[:12]}",
                review_status="approved_with_edits",
                trace_id=trace_id,
                idempotency_key=request.idempotency_key,
                to_email=to_email,
                subject=subject,
                text_body=outbound_content,
                in_reply_to=in_reply_to,
                references=references,
                metadata={
                    "kind": "next_action_reply_send",
                    "source_next_action": session.get("next_best_action"),
                    "unsupported_claims": False,
                    "bench_verified": False,
                    "scheduling_portal_url": scheduling_portal_url,
                },
            )
            result = await self._email_service.send_email(outbound)
            if not result.accepted:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="ORCHESTRATION_FAILED",
                    message=result.error.error_message if result.error else "Failed to send outbound reply.",
                    retryable=bool(result.error.retryable) if result.error else False,
                )
            sent_message_id = result.provider_message_id or f"reply_sent_{uuid4().hex[:12]}"
            reply_to_address = build_lead_reply_address(
                lead_id=request.lead_id,
                domain=self._settings.resend_reply_domain,
            )
            self._state_repo.append_message(
                lead_id=request.lead_id,
                channel="email",
                message_id=sent_message_id,
                direction="outbound",
                content=outbound_content,
                metadata={
                    "kind": "reply_sent",
                    "subject": subject,
                    "to_email": to_email,
                    "in_reply_to": in_reply_to,
                    "references": references,
                    "reply_to_address": reply_to_address,
                    "resend_message_id": result.provider_message_id,
                    "resend_raw_response": result.raw_response or {},
                    "scheduling_portal_url": scheduling_portal_url,
                },
            )
        else:
            if self._sms_service is None:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="CONFIG_ERROR",
                    message="SMSService not configured.",
                    retryable=False,
                )
            to_number = (request.to_number or "").strip() or (self._latest_inbound_sms_number(lead_id=request.lead_id) or "")
            if not to_number:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="INVALID_INPUT",
                    message="Recipient phone number could not be resolved. Provide to_number explicitly.",
                    retryable=False,
                )
            outbound_content = content
            if self._should_include_scheduling_link(session=session, conversation=conversation):
                latest_inbound = self._state_repo.get_latest_inbound_email_for_lead(lead_id=request.lead_id) or {}
                scheduling_portal_url = self._resolve_scheduling_portal_url(
                    lead_id=request.lead_id,
                    meeting_text=None,
                    starts_at=None,
                    prospect_email=str(latest_inbound.get("from_email") or "").strip() or None,
                )
                outbound_content = append_scheduling_cta(
                    content=outbound_content,
                    channel="sms",
                    scheduling_portal_url=scheduling_portal_url,
                )
            sms_request = OutboundSMSRequest(
                lead_id=request.lead_id,
                draft_id=f"reply_sms_draft_{uuid4().hex[:12]}",
                review_id=f"ui_reply_sms_review_{uuid4().hex[:12]}",
                review_status="approved_with_edits",
                trace_id=trace_id,
                idempotency_key=request.idempotency_key,
                to_number=to_number,
                message=outbound_content,
                lead_channel_state=lead_channel_state,
                metadata={
                    "kind": "next_action_reply_send",
                    "source_next_action": session.get("next_best_action"),
                    "unsupported_claims": False,
                    "bench_verified": False,
                    "scheduling_portal_url": scheduling_portal_url,
                },
            )
            sms_result = await self._sms_service.send_warm_lead_sms(sms_request)
            if not sms_result.accepted:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="ORCHESTRATION_FAILED",
                    message=sms_result.error.error_message if sms_result.error else "Failed to send outbound SMS reply.",
                    retryable=bool(sms_result.error.retryable) if sms_result.error else False,
                )
            sent_message_id = sms_result.provider_message_id or f"reply_sms_{uuid4().hex[:12]}"
            self._state_repo.append_message(
                lead_id=request.lead_id,
                channel="sms",
                message_id=sent_message_id,
                direction="outbound",
                content=outbound_content,
                metadata={
                    "kind": "reply_sent",
                    "to_number": to_number,
                    "provider_message_id": sms_result.provider_message_id,
                    "provider_raw_response": sms_result.raw_response or {},
                    "scheduling_portal_url": scheduling_portal_url,
                },
            )
        await self._append_hubspot_channel_handoff_event(
            lead_id=request.lead_id,
            trace_id=trace_id,
            requested_channel=channel,
            resolved_channel=outbound_channel,
            reason=handoff.reason,
            idempotency_key=f"{request.idempotency_key}:handoff",
        )
        if scheduling_portal_url:
            await self._append_hubspot_scheduling_link_event(
                lead_id=request.lead_id,
                trace_id=trace_id,
                channel=outbound_channel,
                scheduling_portal_url=scheduling_portal_url,
                idempotency_key=f"{request.idempotency_key}:sched_link",
            )
        self._state_repo.upsert_conversation_state(
            lead_id=request.lead_id,
            payload={
                **conversation,
                "current_stage": "waiting",
                "current_channel": outbound_channel,
                "last_outbound_message_id": sent_message_id,
                "pending_actions": [{"action_type": "wait_for_reply", "status": "pending"}],
            },
        )
        next_stage = session.get("current_stage", "qualifying")
        try:
            validate_lead_transition(from_state=next_stage, to_state="awaiting_reply")
            next_stage = "awaiting_reply"
        except InvalidStateTransitionError:
            pass
        self._state_repo.upsert_session_state(
            lead_id=request.lead_id,
            payload={
                **session,
                "current_stage": next_stage,
                "next_best_action": "wait_for_reply" if next_stage == "awaiting_reply" else session.get("next_best_action"),
                "current_objective": "wait_for_inbound_reply" if next_stage == "awaiting_reply" else session.get("current_objective"),
                "pending_actions": (
                    [{"action_type": "wait_for_reply", "status": "pending"}]
                    if next_stage == "awaiting_reply"
                    else session.get("pending_actions", [])
                ),
            },
        )
        self._state_repo.update_pipeline_run_stage(
            lead_id=request.lead_id,
            stage=next_stage,
            trace_id=trace_id,
        )
        env = ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={
                "lead_id": request.lead_id,
                "message_id": sent_message_id,
                "delivery_status": "queued",
                "state": next_stage,
                "next_action": "wait_for_reply" if next_stage == "awaiting_reply" else session.get("next_best_action"),
            },
        )
        self._state_repo.put_idempotency_response(
            idempotency_key=request.idempotency_key,
            response=env.model_dump(mode="json"),
        )
        return env

    # SPEC-GAP: specs/api_contracts/scheduling_api.md is empty in this repo.
    # Minimal safe contract added for operator-driven scheduling prepare/book actions.
    async def prepare_scheduling(self, request: LeadSchedulePrepareRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_schedule_prepare_{uuid4().hex[:12]}"
        log_processing_step(
            component="orchestration",
            step="prepare_scheduling.start",
            message="Preparing scheduling context from conversation history",
            lead_id=request.lead_id,
            trace_id=trace_id,
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
        conversation = self._state_repo.get_conversation_state(lead_id=request.lead_id) or {}
        scheduling_ctx = conversation.get("scheduling_context")
        scheduling_ctx_dict = scheduling_ctx if isinstance(scheduling_ctx, dict) else {"booking_status": "none"}
        transcript = self._conversation_transcript_for_reply_routing(lead_id=request.lead_id)
        latest_inbound = self._state_repo.get_latest_inbound_email_for_lead(lead_id=request.lead_id) or {}
        inbound_subject = str(latest_inbound.get("subject") or "").strip()
        inbound_body = (
            str(latest_inbound.get("text_body") or "").strip()
            or str(latest_inbound.get("html_body") or "").strip()
        )
        meeting_text = self._meeting_text_from_scheduling_context(scheduling_ctx_dict)
        meeting_source = "conversation_state" if meeting_text else "none"
        if meeting_text and self._looks_like_outbound_question(meeting_text):
            meeting_text = None
            meeting_source = "none"
        if not meeting_text:
            meeting_text = await self._extract_meeting_time_with_optional_llm(
                lead_id=request.lead_id,
                trace_id=trace_id,
                inbound_subject=inbound_subject,
                inbound_body=inbound_body,
                transcript=transcript,
            )
            meeting_source = "llm_or_heuristic" if meeting_text else "none"

        inferred_starts_at: datetime | None = None
        inferred_timezone: str | None = None
        if meeting_text:
            inferred_starts_at, inferred_timezone = self._resolve_meeting_start_from_text(
                meeting_text=meeting_text,
                timezone_hint=str(scheduling_ctx_dict.get("timezone") or "").strip() or None,
            )
            next_ctx = dict(scheduling_ctx_dict)
            next_ctx.setdefault("booking_status", "none")
            next_ctx["requested_time_text"] = meeting_text
            if inferred_timezone and not next_ctx.get("timezone"):
                next_ctx["timezone"] = inferred_timezone
            slots = next_ctx.get("slots_proposed")
            slots_list: list[Any] = list(slots) if isinstance(slots, list) else []
            if not slots_list:
                slot_payload: dict[str, Any] = {"source": meeting_source, "text": meeting_text}
                if inferred_starts_at is not None:
                    slot_payload["start_at"] = inferred_starts_at.isoformat()
                    slot_payload["end_at"] = (inferred_starts_at + timedelta(minutes=15)).isoformat()
                slots_list = [slot_payload]
            next_ctx["slots_proposed"] = slots_list
            self._state_repo.upsert_conversation_state(
                lead_id=request.lead_id,
                payload={
                    **conversation,
                    "scheduling_context": next_ctx,
                },
            )
            scheduling_ctx_dict = next_ctx

        portal_url = self._resolve_scheduling_portal_url(
            lead_id=request.lead_id,
            meeting_text=meeting_text,
            starts_at=inferred_starts_at,
            prospect_email=str(latest_inbound.get("from_email") or "").strip() or None,
        )
        log_processing_step(
            component="orchestration",
            step="prepare_scheduling.done",
            message="Scheduling context prepared",
            lead_id=request.lead_id,
            trace_id=trace_id,
            meeting_time_text=meeting_text,
            meeting_time_source=meeting_source,
            booking_status=scheduling_ctx_dict.get("booking_status", "none"),
        )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={
                "lead_id": request.lead_id,
                "next_action": session.get("next_best_action"),
                "meeting_time_text": meeting_text,
                "meeting_time_source": meeting_source,
                "meeting_time_start_at": inferred_starts_at.isoformat() if inferred_starts_at is not None else None,
                "meeting_timezone": inferred_timezone or scheduling_ctx_dict.get("timezone"),
                "booking_status": scheduling_ctx_dict.get("booking_status", "none"),
                "scheduling_portal_url": portal_url,
            },
        )

    async def book_scheduling(self, request: LeadScheduleBookRequest) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_schedule_book_{uuid4().hex[:12]}"
        log_processing_step(
            component="orchestration",
            step="book_scheduling.start",
            message="Attempting Cal.com booking from scheduling context",
            lead_id=request.lead_id,
            trace_id=trace_id,
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
        if self._calcom is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="CONFIG_ERROR",
                message="Cal.com service is not configured.",
                retryable=False,
            )
        if not request.confirmed_by_prospect:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="POLICY_BLOCKED",
                message="Booking requires explicit prospect confirmation.",
                retryable=False,
            )

        try:
            validate_lead_transition(from_state=session["current_stage"], to_state="booked")
        except InvalidStateTransitionError as exc:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_STATE_TRANSITION",
                message=str(exc),
                retryable=False,
            )

        conversation = self._state_repo.get_conversation_state(lead_id=request.lead_id) or {}
        scheduling_ctx = conversation.get("scheduling_context")
        scheduling_ctx_dict = scheduling_ctx if isinstance(scheduling_ctx, dict) else {"booking_status": "none"}
        meeting_text = self._meeting_text_from_scheduling_context(scheduling_ctx_dict)

        explicit_start = self._coerce_datetime(request.starts_at_iso)
        inferred_start, inferred_timezone = (
            self._resolve_meeting_start_from_text(
                meeting_text=meeting_text or "",
                timezone_hint=request.timezone or str(scheduling_ctx_dict.get("timezone") or "").strip() or None,
            )
            if explicit_start is None and meeting_text
            else (None, None)
        )
        starts_at = explicit_start or inferred_start
        timezone_text = (
            (request.timezone or "").strip()
            or inferred_timezone
            or str(scheduling_ctx_dict.get("timezone") or "").strip()
            or "UTC"
        )
        if starts_at is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message="Could not resolve a concrete booking time from conversation history. Provide starts_at_iso.",
                retryable=False,
            )

        latest_inbound = self._state_repo.get_latest_inbound_email_for_lead(lead_id=request.lead_id) or {}
        prospect_email = str(latest_inbound.get("from_email") or "").strip()
        if not prospect_email:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message="Prospect email is missing; cannot book Cal event.",
                retryable=False,
            )

        prospect_name = self._prospect_name_from_latest_inbound(latest_inbound)
        ends_at = starts_at + timedelta(minutes=request.duration_minutes)
        booking_request = BookingRequest(
            lead_id=request.lead_id,
            trace_id=trace_id,
            slot_id=f"inferred_{starts_at.isoformat()}",
            starts_at=starts_at,
            ends_at=ends_at,
            timezone=timezone_text,
            prospect_email=prospect_email,
            prospect_name=prospect_name,
            confirmed_by_prospect=True,
            idempotency_key=request.idempotency_key,
        )

        crm_write: CRMWriteResult | None = None
        if self._hubspot is not None:
            pipeline = self._state_repo.get_pipeline_run(lead_id=request.lead_id) or {}
            linked = await book_and_sync_crm(
                lead_id=request.lead_id,
                booking_request=booking_request,
                calcom_service=self._calcom,
                hubspot_service=self._hubspot,
                company_name=str(pipeline.get("company_name") or "").strip() or None,
                company_domain=str(pipeline.get("company_domain") or "").strip() or None,
            )
            booking = linked.booking
            crm_write = linked.crm_write
        else:
            booking = await self._calcom.book_discovery_call(booking_request)

        if not booking.succeeded:
            failed_ctx = dict(scheduling_ctx_dict)
            failed_ctx["booking_status"] = "failed"
            failed_ctx["requested_time_text"] = meeting_text
            self._state_repo.upsert_conversation_state(
                lead_id=request.lead_id,
                payload={
                    **conversation,
                    "current_stage": "scheduling_dialogue",
                    "scheduling_context": failed_ctx,
                },
            )
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="BOOKING_FAILED",
                message=(
                    booking.error.error_message
                    if booking.error is not None
                    else "Booking failed before confirmation."
                ),
                retryable=bool(booking.error.retryable) if booking.error is not None else False,
            )

        next_session = {
            **session,
            "current_stage": "booked",
            "next_best_action": "none",
            "current_objective": "booking_confirmed",
            "pending_actions": [],
            "handoff_required": False,
        }
        self._state_repo.upsert_session_state(lead_id=request.lead_id, payload=next_session)
        booked_ctx = dict(scheduling_ctx_dict)
        booked_ctx["booking_status"] = "confirmed"
        booked_ctx["timezone"] = timezone_text
        booked_ctx["requested_time_text"] = meeting_text
        booked_ctx["slots_proposed"] = [
            {
                "source": "calcom_booking",
                "slot_id": booking.slot_id,
                "start_at": booking.starts_at.isoformat() if booking.starts_at is not None else starts_at.isoformat(),
                "end_at": booking.ends_at.isoformat() if booking.ends_at is not None else ends_at.isoformat(),
                "calendar_ref": booking.calendar_ref,
            }
        ]
        self._state_repo.upsert_conversation_state(
            lead_id=request.lead_id,
            payload={
                **conversation,
                "current_stage": "completed",
                "current_channel": "email",
                "pending_actions": [],
                "scheduling_context": booked_ctx,
            },
        )
        self._state_repo.update_pipeline_run_stage(
            lead_id=request.lead_id,
            stage="booked",
            trace_id=trace_id,
        )
        if self._hubspot is not None:
            await self._hubspot.set_stage(
                lead_id=request.lead_id,
                stage="booked",
                trace_id=trace_id,
                idempotency_key=f"{request.idempotency_key}:stage",
            )
        env = ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={
                "lead_id": request.lead_id,
                "state": "booked",
                "booking_id": booking.booking_id,
                "slot_id": booking.slot_id,
                "calendar_ref": booking.calendar_ref,
                "starts_at": booking.starts_at.isoformat() if booking.starts_at is not None else starts_at.isoformat(),
                "ends_at": booking.ends_at.isoformat() if booking.ends_at is not None else ends_at.isoformat(),
                "timezone": timezone_text,
                "crm_sync_status": crm_write.status if crm_write is not None else "not_configured",
            },
        )
        log_processing_step(
            component="orchestration",
            step="book_scheduling.done",
            message="Booking confirmed and lead marked booked",
            lead_id=request.lead_id,
            trace_id=trace_id,
            booking_id=booking.booking_id,
            crm_status=crm_write.status if crm_write is not None else "not_configured",
        )
        self._state_repo.put_idempotency_response(
            idempotency_key=request.idempotency_key,
            response=env.model_dump(mode="json"),
        )
        return env

    async def handle_email_webhook(
        self,
        *,
        payload: dict[str, Any],
        headers: dict[str, str] | None,
        raw_body: bytes | str | None = None,
    ) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_webhook_{uuid4().hex[:12]}"
        if self._email_service is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="CONFIG_ERROR",
                message="EmailService not configured.",
                retryable=False,
            )

        raw_type = str(payload.get("type") or payload.get("event") or payload.get("event_type") or "").strip().lower()
        if raw_type != "email.received":
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={"event_type": raw_type or "unknown", "processed": False, "ignored": True},
            )

        WEBHOOK_LOGGER.info(
            "resend_email_received_webhook trace_id=%s raw_payload=%s",
            trace_id,
            self._serialize_for_log(payload),
        )

        event = await self._email_service.handle_webhook(payload=payload, headers=headers, raw_body=raw_body)
        WEBHOOK_LOGGER.info(
            "resend_email_received_normalized_event trace_id=%s event=%s",
            trace_id,
            self._serialize_for_log(event.model_dump(mode="json")),
        )
        if event.error is not None:
            log_processing_step(
                component="orchestration",
                step="handle_email_webhook.rejected",
                message="Inbound email.received webhook failed validation",
                trace_id=trace_id,
                payload_ref=event.raw_payload_ref,
                error_code=event.error.error_code,
                error_message=event.error.error_message,
                level=logging.WARNING,
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": raw_type,
                    "processed": False,
                    "reason": event.error.error_code,
                    "raw_payload_ref": event.raw_payload_ref,
                },
            )

        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        email_id = str(data.get("email_id") or event.provider_message_id or "").strip()
        if not email_id:
            log_processing_step(
                component="orchestration",
                step="handle_email_webhook.missing_email_id",
                message="Inbound email.received payload missing data.email_id",
                trace_id=trace_id,
                payload_ref=event.raw_payload_ref,
                level=logging.WARNING,
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={"event_type": raw_type, "processed": False, "reason": "missing_email_id"},
            )

        hydrated_raw = await self._hydrate_received_email(email_id=email_id)
        hydrated = self._extract_received_email_data(hydrated_raw) if isinstance(hydrated_raw, dict) else None
        if hydrated is None:
            log_processing_step(
                component="orchestration",
                step="handle_email_webhook.fetch_failed",
                message="Failed to fetch received email from Resend",
                trace_id=trace_id,
                resend_email_id=email_id,
                level=logging.WARNING,
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": raw_type,
                    "processed": False,
                    "reason": "received_email_fetch_failed",
                    "resend_email_id": email_id,
                },
            )
        WEBHOOK_LOGGER.info(
            "resend_received_email_payload trace_id=%s resend_email_id=%s payload=%s",
            trace_id,
            email_id,
            self._serialize_for_log(hydrated_raw),
        )

        to_address = self._first_email_address(hydrated.get("to"))
        if not to_address or "@" not in to_address:
            log_processing_step(
                component="orchestration",
                step="handle_email_webhook.invalid_to",
                message="Fetched received email has malformed or missing recipient",
                trace_id=trace_id,
                resend_email_id=email_id,
                level=logging.WARNING,
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": raw_type,
                    "processed": False,
                    "reason": "invalid_to_address",
                    "resend_email_id": email_id,
                },
            )

        headers_map = self._normalize_received_headers(hydrated.get("headers"))
        in_reply_to = (
            self._coerce_str(hydrated.get("in_reply_to"))
            or self._coerce_str(hydrated.get("inReplyTo"))
            or headers_map.get("in-reply-to")
        )
        references = self._coerce_str(hydrated.get("references")) or headers_map.get("references")
        lead_id = extract_lead_id_from_reply_address(
            to_address,
            domain=self._settings.resend_reply_domain,
        )
        if not lead_id:
            lead_id = self._state_repo.find_lead_id_by_email_headers(
                in_reply_to=in_reply_to,
                references=references,
            )
        if not lead_id:
            log_processing_step(
                component="orchestration",
                step="handle_email_webhook.unmatched",
                message="Inbound reply could not be matched to a lead",
                trace_id=trace_id,
                payload_ref=event.raw_payload_ref,
                to_email=to_address,
                resend_email_id=email_id,
                level=logging.WARNING,
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": raw_type,
                    "matched": False,
                    "processed": False,
                    "raw_payload_ref": event.raw_payload_ref,
                    "resend_email_id": email_id,
                },
            )

        session = self._state_repo.get_session_state(lead_id=lead_id)
        if session is None:
            log_processing_step(
                component="orchestration",
                step="handle_email_webhook.unknown_lead",
                message="Resolved lead_id is not present in local state",
                trace_id=trace_id,
                lead_id=lead_id,
                resend_email_id=email_id,
                level=logging.WARNING,
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": raw_type,
                    "matched": False,
                    "processed": False,
                    "reason": "unknown_lead",
                    "lead_id": lead_id,
                    "resend_email_id": email_id,
                },
            )

        from_address = self._first_email_address(hydrated.get("from")) or event.from_email
        subject = self._coerce_str(hydrated.get("subject")) or event.subject
        text_body = self._coerce_str(hydrated.get("text")) or event.text_body
        html_body = self._coerce_str(hydrated.get("html")) or event.html_body
        rfc_message_id = normalize_message_id(self._coerce_str(hydrated.get("message_id")) or event.rfc_message_id)
        received_at = self._coerce_datetime(hydrated.get("received_at") or hydrated.get("created_at")) or event.received_at
        normalized_inbound_payload = {
            "leadId": lead_id,
            "from": from_address,
            "to": to_address,
            "subject": subject,
            "text": text_body,
            "html": html_body,
            "headers": headers_map,
            "resendEmailId": email_id,
            "inReplyTo": in_reply_to,
            "references": references,
            "receivedAt": received_at.isoformat(),
        }
        WEBHOOK_LOGGER.info(
            "resend_normalized_inbound_email trace_id=%s resend_email_id=%s payload=%s",
            trace_id,
            email_id,
            self._serialize_for_log(normalized_inbound_payload),
        )
        inserted = self._state_repo.upsert_inbound_email(
            resend_email_id=email_id,
            lead_id=lead_id,
            from_email=from_address,
            to_email=to_address,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            headers=headers_map,
            in_reply_to=in_reply_to,
            references=references,
            received_at=received_at,
        )
        if not inserted:
            log_processing_step(
                component="orchestration",
                step="handle_email_webhook.duplicate",
                message="Duplicate inbound email webhook ignored by idempotent store",
                trace_id=trace_id,
                lead_id=lead_id,
                resend_email_id=email_id,
            )
            existing = self._state_repo.get_inbound_email(resend_email_id=email_id)
            WEBHOOK_LOGGER.info(
                "resend_inbound_duplicate trace_id=%s resend_email_id=%s existing_payload=%s",
                trace_id,
                email_id,
                self._serialize_for_log(existing),
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": raw_type,
                    "processed": False,
                    "duplicate": True,
                    "lead_id": lead_id,
                    "resend_email_id": email_id,
                },
            )

        content = (text_body or html_body or "").strip()
        reply_request = LeadReplyRequest(
            idempotency_key=f"webhook:resend:{email_id}",
            lead_id=lead_id,
            channel="email",
            message_id=email_id,
            content=content or "(empty inbound email)",
            subject=subject,
            rfc_message_id=rfc_message_id,
            references_for_thread=references,
            from_email=from_address,
            received_at=received_at,
        )
        WEBHOOK_LOGGER.info(
            "resend_inbound_reply_request trace_id=%s resend_email_id=%s payload=%s",
            trace_id,
            email_id,
            self._serialize_for_log(reply_request.model_dump(mode="json")),
        )
        reply_env = await self.handle_reply(reply_request)
        WEBHOOK_LOGGER.info(
            "resend_inbound_reply_result trace_id=%s resend_email_id=%s response=%s",
            trace_id,
            email_id,
            self._serialize_for_log(reply_env.model_dump(mode="json")),
        )
        return reply_env

    async def handle_sms_webhook(
        self,
        *,
        payload: dict[str, Any],
        headers: dict[str, str] | None,
        raw_body: bytes | str | None = None,
    ) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_sms_webhook_{uuid4().hex[:12]}"
        if self._sms_service is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="CONFIG_ERROR",
                message="SMSService not configured.",
                retryable=False,
            )
        event = await self._sms_service.handle_inbound_sms(payload=payload, headers=headers, raw_body=raw_body)
        if event.error is not None:
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": event.event_type,
                    "processed": False,
                    "reason": event.error.error_code,
                    "raw_payload_ref": event.raw_payload_ref,
                },
            )
        if event.event_type != "inbound_sms":
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": event.event_type,
                    "processed": True,
                    "raw_payload_ref": event.raw_payload_ref,
                },
            )
        lead_id = self._state_repo.find_lead_by_phone(phone_number=event.from_number)
        if not lead_id:
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={
                    "event_type": event.event_type,
                    "processed": False,
                    "reason": "unknown_lead",
                    "from_number": event.from_number,
                },
            )
        sms_message_id = event.provider_message_id or f"sms_in_{uuid4().hex[:10]}"
        self._state_repo.append_message(
            lead_id=lead_id,
            channel="sms",
            message_id=sms_message_id,
            direction="inbound",
            content=(event.text or "").strip(),
            metadata={
                "from_number": event.from_number,
                "to_number": event.to_number,
                "raw_payload_ref": event.raw_payload_ref,
            },
        )
        reply_request = LeadReplyRequest(
            idempotency_key=f"webhook:africastalking:{event.provider_message_id or event.raw_payload_ref}",
            lead_id=lead_id,
            channel="sms",
            message_id=sms_message_id,
            content=(event.text or "").strip() or "(empty inbound sms)",
            from_number=event.from_number,
            received_at=event.received_at,
        )
        return await self.handle_reply(reply_request)

    async def _hydrate_received_email(
        self,
        *,
        email_id: str,
    ) -> dict[str, Any] | None:
        if self._email_service is None:
            return None
        clean_id = (email_id or "").strip()
        if not clean_id:
            return None
        try:
            received = await self._email_service.get_received_email(email_id=clean_id)
        except Exception:
            return None
        return received if isinstance(received, dict) else None

    @staticmethod
    def _extract_received_email_data(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload

    @staticmethod
    def _normalize_received_headers(raw_headers: Any) -> dict[str, str]:
        normalized: dict[str, str] = {}
        if isinstance(raw_headers, dict):
            for key, value in raw_headers.items():
                if key is None or value is None:
                    continue
                normalized[str(key).strip().lower()] = str(value).strip()
            return normalized
        if isinstance(raw_headers, list):
            for item in raw_headers:
                if not isinstance(item, dict):
                    continue
                key = item.get("name") or item.get("key")
                value = item.get("value")
                if key is None or value is None:
                    continue
                normalized[str(key).strip().lower()] = str(value).strip()
        return normalized

    @staticmethod
    def _first_email_address(raw_value: Any) -> str | None:
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        for value in values:
            if isinstance(value, dict):
                value = value.get("email") or value.get("address") or value.get("value")
            text = OrchestrationRuntime._coerce_str(value)
            if text:
                return text
        return None

    @staticmethod
    def _coerce_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @staticmethod
    def _serialize_for_log(payload: Any) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            return str(payload)

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

    def _conversation_transcript_for_reply_routing(
        self,
        *,
        lead_id: str,
        message_limit: int = 80,
        max_chars: int = 24_000,
        max_message_body_chars: int = 4000,
    ) -> str:
        """Chronological message_log excerpt for reply routing / scheduling context (newest batch, capped)."""
        rows = self._state_repo.list_messages(lead_id=lead_id, limit=message_limit)
        if not rows:
            return ""
        chronological = list(reversed(rows))
        chunks: list[str] = []
        for row in chronological:
            direction = str(row.get("direction") or "?")
            channel = str(row.get("channel") or "?")
            when = str(row.get("recorded_at") or "")
            body = str(row.get("content") or "").strip()
            if len(body) > max_message_body_chars:
                body = body[:max_message_body_chars] + "\n…(truncated)"
            chunks.append(f"[{when}] {direction} {channel}:\n{body}")
        full = "\n\n---\n\n".join(chunks)
        if len(full) > max_chars:
            full = "…(earlier messages omitted)\n\n" + full[-max_chars:]
        return full

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
        requested_channel = (request.channel or "email").strip().lower()
        if requested_channel not in {"email", "sms"}:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unsupported channel '{request.channel}'.",
                retryable=False,
            )
        lead_state = self._channel_state_for_lead(lead_id=request.lead_id)
        handoff = decide_channel_handoff(
            lead_id=request.lead_id,
            requested_channel=requested_channel,
            lead_state=lead_state,
            trace_id=trace_id,
        )
        if not handoff.allowed:
            await self._append_hubspot_channel_handoff_event(
                lead_id=request.lead_id,
                trace_id=trace_id,
                requested_channel=requested_channel,
                resolved_channel=handoff.resolved_channel,
                reason=handoff.reason,
                idempotency_key=f"{idem}:handoff_blocked",
            )
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="POLICY_BLOCKED",
                message=handoff.reason,
                retryable=False,
            )
        scheduling_portal_url: str | None = None
        delivery = "skipped_no_provider"
        msg_id: str | None = None
        if handoff.resolved_channel == "email":
            override_text_body: str | None = None
            if request.include_scheduling_link:
                row = self._state_repo.get_outreach_draft(lead_id=request.lead_id)
                outbound_d = {}
                if row is not None:
                    outbound_d, _ = parse_outreach_stored(row["draft"])
                to_email = (request.to_email or str(outbound_d.get("to_email") or "")).strip() or None
                scheduling_portal_url = self._resolve_scheduling_portal_url(
                    lead_id=request.lead_id,
                    meeting_text=None,
                    starts_at=None,
                    prospect_email=to_email,
                )
                override_text_body = append_scheduling_cta(
                    content=str(outbound_d.get("text_body") or ""),
                    channel="email",
                    scheduling_portal_url=scheduling_portal_url,
                )
            mid, err = await run_outreach_send_for_lead(
                self._outreach_flow_deps(),
                lead_id=request.lead_id,
                draft_id=request.draft_id,
                review_id=request.review_id,
                trace_id=trace_id,
                idempotency_key=idem,
                to_email=request.to_email,
                email_service=self._email_service,
                override_text_body=override_text_body,
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
        else:
            if self._sms_service is None:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="CONFIG_ERROR",
                    message="SMSService not configured.",
                    retryable=False,
                )
            row = self._state_repo.get_outreach_draft(lead_id=request.lead_id)
            if row is None:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="INVALID_INPUT",
                    message=f"No outreach draft for lead_id '{request.lead_id}'.",
                    retryable=False,
                )
            outbound_d, review = parse_outreach_stored(row["draft"])
            outbound = OutboundEmailRequest.model_validate(outbound_d)
            if outbound.draft_id != request.draft_id:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="INVALID_INPUT",
                    message="draft_id mismatch.",
                    retryable=False,
                )
            if not isinstance(review, dict) or review.get("review_id") != request.review_id:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="INVALID_INPUT",
                    message="review_id mismatch.",
                    retryable=False,
                )
            if not review.get("final_send_ok"):
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="POLICY_BLOCKED",
                    message="Review does not allow send (final_send_ok is false).",
                    retryable=False,
                )
            to_number = (request.to_number or "").strip() or (self._latest_inbound_sms_number(lead_id=request.lead_id) or "")
            if not to_number:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="INVALID_INPUT",
                    message="Recipient phone number could not be resolved. Provide to_number explicitly.",
                    retryable=False,
                )
            sms_text = (outbound.text_body or "").strip()
            if request.include_scheduling_link:
                scheduling_portal_url = self._resolve_scheduling_portal_url(
                    lead_id=request.lead_id,
                    meeting_text=None,
                    starts_at=None,
                    prospect_email=(request.to_email or outbound.to_email).strip() or None,
                )
                sms_text = append_scheduling_cta(
                    content=sms_text,
                    channel="sms",
                    scheduling_portal_url=scheduling_portal_url,
                )
            sms_request = OutboundSMSRequest(
                lead_id=request.lead_id,
                draft_id=outbound.draft_id,
                review_id=request.review_id,
                review_status=outbound.review_status,
                trace_id=trace_id,
                idempotency_key=idem,
                to_number=to_number,
                message=sms_text,
                lead_channel_state=lead_state,
                metadata={
                    **(outbound.metadata or {}),
                    "kind": "first_touch_sms",
                    "scheduling_portal_url": scheduling_portal_url,
                },
            )
            sms_result = await self._sms_service.send_warm_lead_sms(sms_request)
            if not sms_result.accepted:
                return self._failure(
                    request_id=request_id,
                    trace_id=trace_id,
                    code="ORCHESTRATION_FAILED",
                    message=sms_result.error.error_message if sms_result.error else "send_failed",
                    retryable=bool(sms_result.error.retryable) if sms_result.error else False,
                )
            self._state_repo.mark_outreach_sent_idempotency(lead_id=request.lead_id, idempotency_key=idem)
            msg_id = sms_result.provider_message_id or f"sms_queued_{idem[-10:]}"
            self._state_repo.append_message(
                lead_id=request.lead_id,
                channel="sms",
                message_id=f"outreach_sms_sent_{idem[:16]}",
                direction="outbound",
                content=sms_text,
                metadata={
                    "kind": "first_touch_sent",
                    "provider_message_id": sms_result.provider_message_id,
                    "draft_id": outbound.draft_id,
                    "review_id": request.review_id,
                    "to_number": to_number,
                    "provider_raw_response": sms_result.raw_response or {},
                    "scheduling_portal_url": scheduling_portal_url,
                },
            )
            delivery = "queued"
        await self._append_hubspot_channel_handoff_event(
            lead_id=request.lead_id,
            trace_id=trace_id,
            requested_channel=requested_channel,
            resolved_channel=handoff.resolved_channel,
            reason=handoff.reason,
            idempotency_key=f"{idem}:handoff",
        )
        if scheduling_portal_url:
            await self._append_hubspot_scheduling_link_event(
                lead_id=request.lead_id,
                trace_id=trace_id,
                channel=handoff.resolved_channel,
                scheduling_portal_url=scheduling_portal_url,
                idempotency_key=f"{idem}:sched_link",
            )
        if delivery == "queued":
            session = self._state_repo.get_session_state(lead_id=request.lead_id)
            if session is not None:
                self._state_repo.upsert_session_state(
                    lead_id=request.lead_id,
                    payload={
                        **session,
                        "current_stage": "awaiting_reply",
                        "next_best_action": "wait_for_reply",
                        "current_objective": "wait_for_inbound_reply",
                        "pending_actions": [{"action_type": "wait_for_reply", "status": "pending"}],
                    },
                )
                self._state_repo.update_pipeline_run_stage(
                    lead_id=request.lead_id,
                    stage="awaiting_reply",
                    trace_id=trace_id,
                )
            conversation = self._state_repo.get_conversation_state(lead_id=request.lead_id) or {}
            self._state_repo.upsert_conversation_state(
                lead_id=request.lead_id,
                payload={
                    **conversation,
                    "current_stage": "waiting",
                    "current_channel": handoff.resolved_channel,
                    "last_outbound_message_id": msg_id,
                    "pending_actions": [{"action_type": "wait_for_reply", "status": "pending"}],
                },
            )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"message_id": msg_id, "delivery_status": delivery},
        )

    def list_outreachs(self, *, limit: int = 200) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_outreachs_{uuid4().hex[:12]}"
        rows = self._state_repo.list_outreach_drafts(limit=limit)
        payload: list[dict[str, Any]] = []
        for row in rows:
            outbound, review = parse_outreach_stored(row["draft"])
            payload.append(
                {
                    "lead_id": row["lead_id"],
                    "company_id": row.get("company_id"),
                    "company_name": row.get("company_name"),
                    "company_domain": row.get("company_domain"),
                    "updated_at": row["updated_at"],
                    "last_send_idempotency": row.get("last_send_idempotency"),
                    "draft_id": outbound.get("draft_id"),
                    "subject": outbound.get("subject"),
                    "to_email": outbound.get("to_email"),
                    "review_status": outbound.get("review_status"),
                    "review_id": review.get("review_id") if isinstance(review, dict) else None,
                    "final_send_ok": review.get("final_send_ok") if isinstance(review, dict) else None,
                }
            )
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"outreachs": payload},
        )

    def get_outreach(self, *, lead_id: str) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_outreach_{uuid4().hex[:12]}"
        row = self._state_repo.get_outreach_draft(lead_id=lead_id)
        if row is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="NOT_FOUND",
                message=f"No outreach draft for lead_id '{lead_id}'.",
                retryable=False,
            )
        outbound, review = parse_outreach_stored(row["draft"])
        run = self._state_repo.get_pipeline_run(lead_id=lead_id) or {}
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={
                "lead_id": lead_id,
                "company_id": run.get("company_id"),
                "company_name": run.get("company_name"),
                "company_domain": run.get("company_domain"),
                "updated_at": row.get("updated_at"),
                "last_send_idempotency": row.get("last_send_idempotency"),
                "outbound": outbound,
                "review": review,
            },
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

    def list_handoffs(self, *, limit: int = 200) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_handoffs_{uuid4().hex[:12]}"
        rows = self._state_repo.list_handoff_queue(limit=limit)
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"handoffs": rows},
        )

    def get_lead_messages(self, *, lead_id: str, limit: int = 200) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_messages_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{lead_id}'.",
                retryable=False,
            )
        rows = self._state_repo.list_messages(lead_id=lead_id, limit=limit)
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"lead_id": lead_id, "messages": rows},
        )

    def get_lead_conversation(self, *, lead_id: str, limit: int = 200) -> ResponseEnvelope:
        request_id = f"req_{uuid4().hex[:10]}"
        trace_id = f"trace_conversation_{uuid4().hex[:12]}"
        session = self._state_repo.get_session_state(lead_id=lead_id)
        if session is None:
            return self._failure(
                request_id=request_id,
                trace_id=trace_id,
                code="INVALID_INPUT",
                message=f"Unknown lead_id '{lead_id}'.",
                retryable=False,
            )
        conversation = self._state_repo.get_conversation_state(lead_id=lead_id)
        messages = self._state_repo.list_messages(lead_id=lead_id, limit=limit)
        pipeline = self._state_repo.get_pipeline_run(lead_id=lead_id)
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={
                "lead_id": lead_id,
                "session_state": session,
                "conversation_state": conversation,
                "messages": messages,
                "pipeline": pipeline,
            },
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
        reply_to_address = str(meta.get("reply_to_address") or "").strip() or build_lead_reply_address(
            lead_id=request.lead_id,
            domain=self._settings.resend_reply_domain,
        )
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
                "reply_to_address": reply_to_address,
                "resend_raw_response": res.raw_response or {},
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
