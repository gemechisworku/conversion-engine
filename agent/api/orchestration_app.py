"""REST orchestration API (specs/api_contracts/orchestration_api.md)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from agent.api.middleware import OrchestrationAPIKeyMiddleware, add_orchestration_cors
from agent.config.settings import get_settings
from agent.main import build_orchestration_runtime
from agent.services.orchestration.schemas import (
    LeadAdvanceRequest,
    LeadCompactRequest,
    LeadEscalationRequest,
    LeadProcessRequest,
    LeadRespondRequest,
    LeadRehydrateRequest,
    LeadReplyRequest,
    MemorySessionWriteRequest,
    OutreachDraftRequest,
    OutreachReviewRequest,
    OutreachSendRequest,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.runtime = build_orchestration_runtime()
    yield


def create_orchestration_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Tenacious Orchestration",
        description=(
            "REST API for lead intake, outreach, memory, and replies. "
            "Optional `ORCHESTRATION_API_KEY`: when set, send `X-API-Key` or `Authorization: Bearer <token>` "
            "on every request except `/health`, `/docs`, `/openapi.json`, and `/redoc`. "
            "Optional `ORCHESTRATION_CORS_ORIGINS`: comma-separated browser origins for SPA access."
        ),
        lifespan=_lifespan,
        openapi_tags=[
            {"name": "meta", "description": "Health (no API key)."},
            {"name": "leads", "description": "Lead intake, state, replies, escalation, compaction."},
            {"name": "pipelines", "description": "Frontend pipeline runs list and cleanup controls."},
            {"name": "outreach", "description": "Draft, review, send."},
            {"name": "outreachs", "description": "List and inspect persisted outreach records."},
            {"name": "memory", "description": "Session, evidence edges, memory compaction."},
        ],
    )

    @app.get("/health", tags=["meta"], summary="Liveness")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "tenacious-orchestration"}

    @app.post("/lead/process", tags=["leads"])
    async def post_lead_process(req: LeadProcessRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.process_lead(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/reply", tags=["leads"])
    async def post_lead_reply(req: LeadReplyRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.handle_reply(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/respond", tags=["leads"])
    async def post_lead_respond(req: LeadRespondRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.respond_to_lead(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post(settings.webhook_route_resend, tags=["leads"])
    async def post_resend_webhook(request: Request) -> JSONResponse:
        raw_body = await request.body()
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                payload = {"payload": payload}
        except Exception:
            payload = {}
        env = await request.app.state.runtime.handle_email_webhook(
            payload=payload,
            headers=dict(request.headers),
            raw_body=raw_body,
        )
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/advance", tags=["leads"])
    async def post_lead_advance(req: LeadAdvanceRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.advance_state(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/lead/{lead_id}/state", tags=["leads"])
    async def get_lead_state(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.get_state(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/lead/{lead_id}/briefs", tags=["leads"])
    async def get_lead_briefs(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.get_lead_briefs(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/lead/{lead_id}/messages", tags=["leads"])
    async def get_lead_messages(
        lead_id: str,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500, description="Max message rows (newest first)")] = 200,
    ) -> JSONResponse:
        env = request.app.state.runtime.get_lead_messages(lead_id=lead_id, limit=limit)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/lead/{lead_id}/conversation", tags=["leads"])
    async def get_lead_conversation(
        lead_id: str,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500, description="Max message rows (newest first)")] = 200,
    ) -> JSONResponse:
        env = request.app.state.runtime.get_lead_conversation(lead_id=lead_id, limit=limit)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/pipelines", tags=["pipelines"])
    async def get_pipelines(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500, description="Max pipeline rows (newest first)")] = 200,
    ) -> JSONResponse:
        env = request.app.state.runtime.list_pipelines(limit=limit)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/pipelines/{lead_id}", tags=["pipelines"])
    async def get_pipeline(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.get_pipeline(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.delete("/pipelines/{lead_id}", tags=["pipelines"])
    async def delete_pipeline(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.delete_pipeline(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/handoffs", tags=["pipelines"])
    async def get_handoffs(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500, description="Max handoff rows (newest first)")] = 200,
    ) -> JSONResponse:
        env = request.app.state.runtime.list_handoffs(limit=limit)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/escalate", tags=["leads"])
    async def post_lead_escalate(req: LeadEscalationRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.escalate(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/compact", tags=["leads"])
    async def post_lead_compact(req: LeadCompactRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.compact_context(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/rehydrate", tags=["leads"])
    async def post_lead_rehydrate(req: LeadRehydrateRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.rehydrate_context(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/outreach/draft", tags=["outreach"])
    async def post_outreach_draft(req: OutreachDraftRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.outreach_draft(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/outreach/review", tags=["outreach"])
    async def post_outreach_review(req: OutreachReviewRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.outreach_review(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/outreach/send", tags=["outreach"])
    async def post_outreach_send(req: OutreachSendRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.outreach_send(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/outreachs", tags=["outreachs"])
    async def get_outreachs(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500, description="Max outreach rows (newest first)")] = 200,
    ) -> JSONResponse:
        env = request.app.state.runtime.list_outreachs(limit=limit)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/outreachs/{lead_id}", tags=["outreachs"])
    async def get_outreach(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.get_outreach(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/memory/session/write", tags=["memory"])
    async def post_memory_session_write(req: MemorySessionWriteRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.memory_session_write(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/memory/session/{lead_id}", tags=["memory"])
    async def get_memory_session(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.memory_session_get(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/memory/evidence/{lead_id}", tags=["memory"])
    async def get_memory_evidence(
        lead_id: str,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500, description="Max evidence rows (newest first)")] = 200,
    ) -> JSONResponse:
        env = request.app.state.runtime.memory_evidence_list(lead_id=lead_id, limit=limit)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/memory/compact", tags=["memory"])
    async def post_memory_compact(req: LeadCompactRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.compact_context(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/memory/rehydrate", tags=["memory"])
    async def post_memory_rehydrate(req: LeadRehydrateRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.rehydrate_context(req)
        return JSONResponse(env.model_dump(mode="json"))

    # API key inner; CORS outer (last registered = runs first on the request).
    app.add_middleware(OrchestrationAPIKeyMiddleware, settings=settings)
    add_orchestration_cors(app, settings=settings)
    return app


app = create_orchestration_app()
