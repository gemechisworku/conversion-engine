"""HTTP middleware for orchestration API (optional API key, shared with CORS order)."""

from __future__ import annotations

from typing import Callable
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agent.api.security import extract_client_api_key, is_browser_preflight, public_paths
from agent.config.settings import Settings
from agent.services.common.schemas import ErrorEnvelope
from agent.services.orchestration.schemas import ResponseEnvelope


def _unauthorized_json(*, message: str) -> JSONResponse:
    rid = f"req_{uuid4().hex[:10]}"
    tid = f"trace_auth_{uuid4().hex[:10]}"
    body = ResponseEnvelope(
        request_id=rid,
        trace_id=tid,
        status="failure",
        error=ErrorEnvelope(
            error_code="UNAUTHORIZED",
            error_message=message,
            retryable=False,
        ),
    ).model_dump(mode="json")
    return JSONResponse(status_code=401, content=body)


class OrchestrationAPIKeyMiddleware(BaseHTTPMiddleware):
    """When `ORCHESTRATION_API_KEY` is set, require it on all routes except health and OpenAPI."""

    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self._expected = (settings.orchestration_api_key or "").strip()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if is_browser_preflight(request):
            return await call_next(request)
        path = request.url.path.rstrip("/") or "/"
        # tolerate trailing-slash variants for public paths
        if path in public_paths() or request.url.path in public_paths():
            return await call_next(request)
        if not self._expected:
            return await call_next(request)
        got = extract_client_api_key(request)
        if got != self._expected:
            return _unauthorized_json(
                message="Valid X-API-Key or Authorization: Bearer token required.",
            )
        return await call_next(request)


def add_orchestration_cors(app, *, settings: Settings) -> None:
    """Register Starlette CORSMiddleware when ORCHESTRATION_CORS_ORIGINS is non-empty."""
    from starlette.middleware.cors import CORSMiddleware

    from agent.api.security import parse_cors_origins

    origins = parse_cors_origins(settings.orchestration_cors_origins)
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
