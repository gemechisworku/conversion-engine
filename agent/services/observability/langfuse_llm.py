"""Optional Langfuse generation spans around OpenRouter calls."""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Iterator
from typing import Any

from agent.config.settings import Settings

LOGGER = logging.getLogger("agent.observability.langfuse")


@contextlib.contextmanager
def langfuse_openrouter_generation(
    settings: Settings,
    *,
    trace_id: str | None,
    lead_id: str | None,
    purpose: str,
    model: str,
) -> Iterator[Any]:
    if not settings.langfuse_public_key.strip() or not settings.langfuse_secret_key.strip():
        yield None
        return
    try:
        from langfuse import Langfuse
        from langfuse.types import TraceContext
    except ImportError:
        yield None
        return
    client: Any = None
    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key.strip(),
            secret_key=settings.langfuse_secret_key.strip(),
            host=(settings.langfuse_host or "https://cloud.langfuse.com").strip(),
        )
        tid = (trace_id or "").strip() or client.create_trace_id()
        span_cm = client.start_as_current_observation(
            trace_context=TraceContext(trace_id=tid),
            name=purpose,
            as_type="generation",
            model=model,
            input={"purpose": purpose, "lead_id": lead_id},
            end_on_exit=True,
        )
    except Exception as exc:  # pragma: no cover - optional telemetry
        LOGGER.debug("Langfuse client unavailable: %s", exc)
        yield None
        return
    with span_cm as obs:
        try:
            yield obs
        finally:
            try:
                client.flush()
            except Exception:
                pass


@contextlib.contextmanager
def langfuse_workflow_span(
    settings: Settings,
    *,
    trace_id: str | None,
    lead_id: str | None,
    name: str,
) -> Iterator[Any]:
    """Top-level workflow span (graphs, outreach steps, orchestration handlers)."""
    if not settings.langfuse_public_key.strip() or not settings.langfuse_secret_key.strip():
        yield None
        return
    try:
        from langfuse import Langfuse
        from langfuse.types import TraceContext
    except ImportError:
        yield None
        return
    client: Any = None
    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key.strip(),
            secret_key=settings.langfuse_secret_key.strip(),
            host=(settings.langfuse_host or "https://cloud.langfuse.com").strip(),
        )
        tid = (trace_id or "").strip() or client.create_trace_id()
        span_cm = client.start_as_current_observation(
            trace_context=TraceContext(trace_id=tid),
            name=name,
            as_type="span",
            input={"lead_id": lead_id, "trace_id": trace_id},
            end_on_exit=True,
        )
    except Exception as exc:  # pragma: no cover
        LOGGER.debug("Langfuse workflow span skipped: %s", exc)
        yield None
        return
    with span_cm as obs:
        try:
            yield obs
        finally:
            try:
                client.flush()
            except Exception:
                pass


def update_langfuse_generation_success(
    obs: Any,
    *,
    parsed_output: dict[str, Any],
    usage: dict[str, Any] | None,
) -> None:
    if obs is None:
        return
    try:
        preview = json.dumps(parsed_output, default=str)[:8000]
        obs.update(output=preview)
        if isinstance(usage, dict):
            obs.update(
                usage_details={
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                }
            )
    except Exception:
        pass
