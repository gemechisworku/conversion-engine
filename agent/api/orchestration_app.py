"""REST orchestration API (specs/api_contracts/orchestration_api.md)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.main import build_orchestration_runtime
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
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.runtime = build_orchestration_runtime()
    yield


def create_orchestration_app() -> FastAPI:
    app = FastAPI(title="Tenacious Orchestration", lifespan=_lifespan)

    @app.post("/lead/process")
    async def post_lead_process(req: LeadProcessRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.process_lead(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/reply")
    async def post_lead_reply(req: LeadReplyRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.handle_reply(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/advance")
    async def post_lead_advance(req: LeadAdvanceRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.advance_state(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/lead/{lead_id}/state")
    async def get_lead_state(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.get_state(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/escalate")
    async def post_lead_escalate(req: LeadEscalationRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.escalate(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/compact")
    async def post_lead_compact(req: LeadCompactRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.compact_context(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/lead/rehydrate")
    async def post_lead_rehydrate(req: LeadRehydrateRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.rehydrate_context(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/outreach/draft")
    async def post_outreach_draft(req: OutreachDraftRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.outreach_draft(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/outreach/review")
    async def post_outreach_review(req: OutreachReviewRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.outreach_review(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/outreach/send")
    async def post_outreach_send(req: OutreachSendRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.outreach_send(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/memory/session/write")
    async def post_memory_session_write(req: MemorySessionWriteRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.memory_session_write(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/memory/session/{lead_id}")
    async def get_memory_session(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.memory_session_get(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.get("/memory/evidence/{lead_id}")
    async def get_memory_evidence(lead_id: str, request: Request) -> JSONResponse:
        env = request.app.state.runtime.memory_evidence_list(lead_id=lead_id)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/memory/compact")
    async def post_memory_compact(req: LeadCompactRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.compact_context(req)
        return JSONResponse(env.model_dump(mode="json"))

    @app.post("/memory/rehydrate")
    async def post_memory_rehydrate(req: LeadRehydrateRequest, request: Request) -> JSONResponse:
        env = await request.app.state.runtime.rehydrate_context(req)
        return JSONResponse(env.model_dump(mode="json"))

    return app


app = create_orchestration_app()
