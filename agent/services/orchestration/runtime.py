"""Runtime orchestration handlers aligned to orchestration API contracts."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent.config.settings import Settings
from agent.graphs.lead_intake_langgraph import LeadIntakeGraphDeps, compile_lead_intake_graph
from agent.graphs.state import LeadGraphState
from agent.graphs.transitions import InvalidStateTransitionError, validate_lead_transition
from agent.repositories.state_repo import SQLiteStateRepository
from agent.services.common.schemas import ErrorEnvelope
from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.conversation.email_llm import interpret_inbound_email_and_draft_reply
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.services.observability.events import log_processing_step, log_trace_event
from agent.services.orchestration.schemas import (
    LeadAdvanceRequest,
    LeadEscalationRequest,
    LeadProcessRequest,
    LeadReplyRequest,
    ResponseEnvelope,
)

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
    ) -> None:
        self._settings = settings
        self._state_repo = state_repo
        self._enrichment_services = enrichment_services
        self._hubspot = hubspot_service
        self._lead_intake_graph = compile_lead_intake_graph(
            LeadIntakeGraphDeps(
                hubspot=self._hubspot,
                enrichment_services=self._enrichment_services,
                state_repo=self._state_repo,
            )
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
        try:
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
                message="Invoking lead intake LangGraph (enrich → crm_sync)",
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

            log_trace_event(
                event_type="lead_processed",
                trace_id=trace_id,
                lead_id=lead_id,
                status="success",
                payload={"company_id": request.company_id},
            )
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data={"lead_id": lead_id, "state": "brief_ready"},
            )
        except InvalidStateTransitionError as exc:
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
        try:
            validate_lead_transition(from_state=session["current_stage"], to_state="reply_received")
            self._state_repo.append_message(
                lead_id=request.lead_id,
                channel=request.channel,
                message_id=request.message_id,
                direction="inbound",
                content=request.content,
                metadata={
                    "received_at": request.received_at.isoformat(),
                    "subject": request.subject,
                },
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
            intent = self._classify_intent(request.content)
            next_action = self._next_action(intent=intent)
            email_interp = None
            llm = self._enrichment_services.get("llm")
            if (
                request.channel.lower() == "email"
                and llm is not None
                and getattr(llm, "configured", False)
            ):
                briefs_all = self._state_repo.get_briefs(lead_id=request.lead_id) or {}
                hiring = briefs_all.get("hiring_signal_brief")
                recent_ctx = self._recent_outbound_email_snippet(lead_id=request.lead_id)
                company_nm = request.company_name or ""
                email_interp = await interpret_inbound_email_and_draft_reply(
                    settings=self._settings,
                    llm=llm,
                    company_name=company_nm,
                    inbound_subject=request.subject or "(no subject)",
                    inbound_body=request.content,
                    recent_outbound_context=recent_ctx,
                    hiring_signal_brief=hiring if isinstance(hiring, dict) else {},
                    trace_id=trace_id,
                    lead_id=request.lead_id,
                )
                if email_interp is not None:
                    intent = email_interp.intent
                    next_action = email_interp.next_best_action
                    allowed_actions = {
                        "schedule",
                        "qualify",
                        "clarify",
                        "handle_objection",
                        "nurture",
                        "escalate",
                    }
                    if next_action not in allowed_actions:
                        next_action = self._next_action(intent=intent)
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
                        },
                    )
            if next_action == "escalate":
                next_state = "handoff_required"
            elif next_action == "schedule":
                next_state = "scheduling"
            else:
                next_state = "qualifying"
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
                    "pending_actions": [{"action_type": next_action, "status": "pending"}],
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
                    "qualification_status": "likely_qualified" if intent in {"interest", "schedule"} else "unknown",
                    "pending_actions": [{"action_type": next_action, "status": "pending"}],
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
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="accepted",
                data=reply_data,
            )
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
        try:
            if session["current_stage"] != request.from_state:
                raise InvalidStateTransitionError(from_state=session["current_stage"], to_state=request.to_state)
            validate_lead_transition(from_state=request.from_state, to_state=request.to_state)
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
            return ResponseEnvelope(
                request_id=request_id,
                trace_id=trace_id,
                status="success",
                data={"lead_id": request.lead_id, "current_state": request.to_state},
            )
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
            },
        )

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
        return ResponseEnvelope(
            request_id=request_id,
            trace_id=trace_id,
            status="success",
            data={"lead_id": request.lead_id, "state": "handoff_required", "handoff_id": f"handoff_{uuid4().hex[:10]}"},
        )

    @staticmethod
    def _lead_id_for_company(*, company_id: str) -> str:
        digest = hashlib.sha256(company_id.encode("utf-8")).hexdigest()[:10]
        return f"lead_{digest}"

    @staticmethod
    def _classify_intent(content: str) -> str:
        lowered = content.lower()
        if any(token in lowered for token in ("book", "schedule", "calendar", "time")):
            return "schedule"
        if any(token in lowered for token in ("not interested", "stop", "no thanks")):
            return "decline"
        if any(token in lowered for token in ("price", "cost", "quote", "proposal")):
            return "objection"
        if "?" in lowered:
            return "clarification"
        if any(token in lowered for token in ("yes", "interested", "sounds good")):
            return "interest"
        return "unclear"

    @staticmethod
    def _next_action(*, intent: str) -> str:
        mapping = {
            "schedule": "schedule",
            "interest": "qualify",
            "clarification": "clarify",
            "objection": "handle_objection",
            "decline": "nurture",
            "unclear": "clarify",
        }
        return mapping.get(intent, "clarify")

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
