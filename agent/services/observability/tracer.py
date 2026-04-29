"""Local JSONL tracer with parent-child run propagation."""

from __future__ import annotations

import contextvars
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .redaction import redact_value
from .schemas import TraceError, TraceEventType, TraceMetadata, TraceRecord

_TRACE_ID_VAR: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_RUN_STACK_VAR: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar("run_stack", default=())


class JsonlTracer:
    """Best-effort tracer for eval/trace_log.jsonl."""

    def __init__(self, *, output_path: str | Path = "eval/trace_log.jsonl") -> None:
        self._output_path = Path(output_path)
        self._write_lock = threading.Lock()
        self._run_start_monotonic: dict[str, float] = {}

    def start_trace(
        self,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        graph_name: str | None = None,
        lead_id: str | None = None,
        company_id: str | None = None,
        session_id: str | None = None,
        input_data: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, str | None]:
        try:
            resolved_trace_id = trace_id or self.current_trace_id() or self._new_trace_id()
            resolved_run_id = run_id or self._new_run_id()
            resolved_parent = parent_run_id or self.current_run_id()
            self._set_context(trace_id=resolved_trace_id, run_id=resolved_run_id)
            self._run_start_monotonic[resolved_run_id] = time.monotonic()
            self.log_event(
                trace_id=resolved_trace_id,
                run_id=resolved_run_id,
                parent_run_id=resolved_parent,
                event_type="graph_start",
                graph_name=graph_name,
                lead_id=lead_id,
                company_id=company_id,
                session_id=session_id,
                input_data=input_data,
                metadata={**(metadata or {}), "status": "success"},
            )
            return {
                "trace_id": resolved_trace_id,
                "run_id": resolved_run_id,
                "parent_run_id": resolved_parent,
            }
        except Exception:
            return {"trace_id": trace_id, "run_id": run_id, "parent_run_id": parent_run_id}

    def end_trace(
        self,
        *,
        trace_id: str,
        run_id: str,
        parent_run_id: str | None = None,
        graph_name: str | None = None,
        lead_id: str | None = None,
        company_id: str | None = None,
        session_id: str | None = None,
        output_data: Any | None = None,
        status: str = "success",
        error: dict[str, Any] | None = None,
    ) -> None:
        try:
            duration = self._duration_ms_for(run_id)
            self.log_event(
                trace_id=trace_id,
                run_id=run_id,
                parent_run_id=parent_run_id,
                event_type="graph_end",
                duration_ms=duration,
                graph_name=graph_name,
                lead_id=lead_id,
                company_id=company_id,
                session_id=session_id,
                output_data=output_data,
                metadata={"status": status, "latency_ms": duration},
                error=error,
            )
            self._pop_run_if_current(run_id)
        except Exception:
            return

    def log_event(
        self,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        event_type: TraceEventType,
        duration_ms: int = 0,
        graph_name: str | None = None,
        node_name: str | None = None,
        agent_name: str | None = None,
        subagent_name: str | None = None,
        lead_id: str | None = None,
        company_id: str | None = None,
        session_id: str | None = None,
        state_before: Any | None = None,
        state_after: Any | None = None,
        input_data: Any | None = None,
        output_data: Any | None = None,
        metadata: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        try:
            resolved_trace_id = trace_id or self.current_trace_id() or self._new_trace_id()
            resolved_run_id = run_id or self.current_run_id() or self._new_run_id()
            resolved_parent = parent_run_id if parent_run_id is not None else self.current_run_id()

            record = TraceRecord(
                trace_id=resolved_trace_id,
                run_id=resolved_run_id,
                parent_run_id=resolved_parent if resolved_parent != resolved_run_id else None,
                event_id=self._new_event_id(),
                event_type=event_type,
                timestamp=self._utc_now_iso(),
                duration_ms=max(0, int(duration_ms)),
                graph_name=graph_name,
                node_name=node_name,
                agent_name=agent_name,
                subagent_name=subagent_name,
                lead_id=lead_id,
                company_id=company_id,
                session_id=session_id,
                state_before=self._to_object(state_before),
                state_after=self._to_object(state_after),
                input=self._to_object(input_data),
                output=self._to_object(output_data),
                metadata=TraceMetadata.model_validate(metadata or {}),
                error=TraceError.model_validate(error) if isinstance(error, dict) else None,
            )
            safe = redact_value(record.model_dump(mode="json"))
            self._append_jsonl(safe)
        except Exception:
            return

    def log_node_start(
        self,
        *,
        trace_id: str | None,
        node_name: str,
        graph_name: str | None = None,
        lead_id: str | None = None,
        company_id: str | None = None,
        session_id: str | None = None,
        parent_run_id: str | None = None,
        input_data: Any | None = None,
    ) -> str | None:
        try:
            run_id = self._new_run_id()
            resolved_parent = parent_run_id or self.current_run_id()
            self._set_context(trace_id=trace_id, run_id=run_id)
            self._run_start_monotonic[run_id] = time.monotonic()
            self.log_event(
                trace_id=trace_id,
                run_id=run_id,
                parent_run_id=resolved_parent,
                event_type="node_start",
                graph_name=graph_name,
                node_name=node_name,
                lead_id=lead_id,
                company_id=company_id,
                session_id=session_id,
                input_data=input_data,
                metadata={"status": "success"},
            )
            return run_id
        except Exception:
            return None

    def log_node_end(
        self,
        *,
        trace_id: str | None,
        run_id: str | None,
        node_name: str,
        graph_name: str | None = None,
        lead_id: str | None = None,
        company_id: str | None = None,
        session_id: str | None = None,
        output_data: Any | None = None,
        status: str = "success",
        error: dict[str, Any] | None = None,
    ) -> None:
        if not run_id:
            return
        try:
            duration = self._duration_ms_for(run_id)
            self.log_event(
                trace_id=trace_id,
                run_id=run_id,
                parent_run_id=self.parent_for(run_id),
                event_type="node_end",
                duration_ms=duration,
                graph_name=graph_name,
                node_name=node_name,
                lead_id=lead_id,
                company_id=company_id,
                session_id=session_id,
                output_data=output_data,
                metadata={"status": status, "latency_ms": duration},
                error=error,
            )
            self._pop_run_if_current(run_id)
        except Exception:
            return

    def log_tool_start(
        self,
        *,
        trace_id: str | None,
        tool_name: str,
        lead_id: str | None = None,
        parent_run_id: str | None = None,
        input_data: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        try:
            run_id = self._new_run_id()
            resolved_parent = parent_run_id or self.current_run_id()
            self._set_context(trace_id=trace_id, run_id=run_id)
            self._run_start_monotonic[run_id] = time.monotonic()
            data = dict(metadata or {})
            data["tool_name"] = tool_name
            data.setdefault("status", "success")
            self.log_event(
                trace_id=trace_id,
                run_id=run_id,
                parent_run_id=resolved_parent,
                event_type="tool_start",
                lead_id=lead_id,
                input_data=input_data,
                metadata=data,
            )
            return run_id
        except Exception:
            return None

    def log_tool_end(
        self,
        *,
        trace_id: str | None,
        run_id: str | None,
        tool_name: str,
        lead_id: str | None = None,
        output_data: Any | None = None,
        status: str = "success",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not run_id:
            return
        try:
            duration = self._duration_ms_for(run_id)
            data = dict(metadata or {})
            data["tool_name"] = tool_name
            data["status"] = status
            data.setdefault("latency_ms", duration)
            self.log_event(
                trace_id=trace_id,
                run_id=run_id,
                parent_run_id=self.parent_for(run_id),
                event_type="tool_end",
                duration_ms=duration,
                lead_id=lead_id,
                output_data=output_data,
                metadata=data,
            )
            self._pop_run_if_current(run_id)
        except Exception:
            return

    def log_tool_error(
        self,
        *,
        trace_id: str | None,
        run_id: str | None,
        tool_name: str,
        lead_id: str | None = None,
        error: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not run_id:
            return
        try:
            duration = self._duration_ms_for(run_id)
            data = dict(metadata or {})
            data["tool_name"] = tool_name
            data["status"] = "failure"
            data.setdefault("latency_ms", duration)
            self.log_event(
                trace_id=trace_id,
                run_id=run_id,
                parent_run_id=self.parent_for(run_id),
                event_type="tool_error",
                duration_ms=duration,
                lead_id=lead_id,
                metadata=data,
                error=error,
            )
            self._pop_run_if_current(run_id)
        except Exception:
            return

    def log_state_transition(
        self,
        *,
        trace_id: str | None,
        run_id: str | None = None,
        lead_id: str | None = None,
        state_before: Any | None = None,
        state_after: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.log_event(
            trace_id=trace_id,
            run_id=run_id,
            parent_run_id=self.current_run_id(),
            event_type="state_transition",
            lead_id=lead_id,
            state_before=state_before,
            state_after=state_after,
            metadata=metadata or {"status": "success"},
        )

    def log_policy_decision(
        self,
        *,
        trace_id: str | None,
        run_id: str | None = None,
        lead_id: str | None = None,
        input_data: Any | None = None,
        output_data: Any | None = None,
        status: str = "success",
    ) -> None:
        self.log_event(
            trace_id=trace_id,
            run_id=run_id,
            parent_run_id=self.current_run_id(),
            event_type="policy_decision",
            lead_id=lead_id,
            input_data=input_data,
            output_data=output_data,
            metadata={"status": status},
        )

    def current_trace_id(self) -> str | None:
        return _TRACE_ID_VAR.get()

    def current_run_id(self) -> str | None:
        stack = _RUN_STACK_VAR.get()
        if not stack:
            return None
        return stack[-1]

    def parent_for(self, run_id: str) -> str | None:
        stack = _RUN_STACK_VAR.get()
        if len(stack) < 2:
            return None
        if stack[-1] != run_id:
            return stack[-1]
        return stack[-2]

    def _append_jsonl(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock:
            with self._output_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
                handle.flush()

    def _set_context(self, *, trace_id: str | None, run_id: str) -> None:
        if trace_id:
            _TRACE_ID_VAR.set(trace_id)
        stack = _RUN_STACK_VAR.get()
        _RUN_STACK_VAR.set((*stack, run_id))

    def _pop_run_if_current(self, run_id: str) -> None:
        stack = _RUN_STACK_VAR.get()
        if not stack or stack[-1] != run_id:
            return
        _RUN_STACK_VAR.set(stack[:-1])
        self._run_start_monotonic.pop(run_id, None)

    def _duration_ms_for(self, run_id: str) -> int:
        started = self._run_start_monotonic.get(run_id)
        if started is None:
            return 0
        return max(0, int((time.monotonic() - started) * 1000))

    @staticmethod
    def _to_object(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return {"value": value}

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _new_trace_id() -> str:
        return f"trace_{uuid4().hex}"

    @staticmethod
    def _new_run_id() -> str:
        return f"run_{uuid4().hex}"

    @staticmethod
    def _new_event_id() -> str:
        return f"evt_{uuid4().hex}"

