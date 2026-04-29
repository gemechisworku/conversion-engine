from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from agent.services.observability.tracer import JsonlTracer


def _read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _local_trace_file() -> Path:
    root = Path("outputs") / "pytest_local" / f"trace_{uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    return root / "eval" / "trace_log.jsonl"


def _cleanup(path: Path) -> None:
    base = path.parent.parent
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)


def test_tracer_creates_trace_log_file() -> None:
    trace_file = _local_trace_file()
    tracer = JsonlTracer(output_path=trace_file)
    tracer.log_event(trace_id="trace_a", run_id="run_a", event_type="agent_start")

    assert trace_file.exists()
    rows = _read_jsonl(trace_file)
    assert len(rows) == 1
    _cleanup(trace_file)


def test_tracer_writes_valid_jsonl() -> None:
    trace_file = _local_trace_file()
    tracer = JsonlTracer(output_path=trace_file)
    tracer.log_event(trace_id="trace_a", run_id="run_1", event_type="graph_start", graph_name="lead_graph")
    tracer.log_event(trace_id="trace_a", run_id="run_1", event_type="graph_end", graph_name="lead_graph")

    rows = _read_jsonl(trace_file)
    assert rows[0]["event_type"] == "graph_start"
    assert rows[1]["event_type"] == "graph_end"
    _cleanup(trace_file)


def test_parent_child_run_ids() -> None:
    trace_file = _local_trace_file()
    tracer = JsonlTracer(output_path=trace_file)

    graph_ctx = tracer.start_trace(trace_id="trace_parent", graph_name="lead_graph")
    node_run = tracer.log_node_start(
        trace_id="trace_parent",
        node_name="enrich",
        graph_name="lead_graph",
        parent_run_id=graph_ctx["run_id"],
    )
    tracer.log_node_end(trace_id="trace_parent", run_id=node_run, node_name="enrich", graph_name="lead_graph")
    tracer.end_trace(trace_id="trace_parent", run_id=graph_ctx["run_id"], graph_name="lead_graph")

    rows = _read_jsonl(trace_file)
    node_start = next(row for row in rows if row["event_type"] == "node_start")
    assert node_start["parent_run_id"] == graph_ctx["run_id"]
    _cleanup(trace_file)


def test_tool_success_and_error_events() -> None:
    trace_file = _local_trace_file()
    tracer = JsonlTracer(output_path=trace_file)

    success_run = tracer.log_tool_start(trace_id="trace_tool", tool_name="send_email", lead_id="lead_1")
    tracer.log_tool_end(
        trace_id="trace_tool",
        run_id=success_run,
        tool_name="send_email",
        lead_id="lead_1",
        output_data={"provider_message_id": "msg_1"},
    )
    error_run = tracer.log_tool_start(trace_id="trace_tool", tool_name="send_sms", lead_id="lead_1")
    tracer.log_tool_error(
        trace_id="trace_tool",
        run_id=error_run,
        tool_name="send_sms",
        lead_id="lead_1",
        error={"type": "DeliveryError", "message": "provider down", "retryable": True},
    )

    rows = _read_jsonl(trace_file)
    assert any(row["event_type"] == "tool_end" for row in rows)
    assert any(row["event_type"] == "tool_error" for row in rows)
    _cleanup(trace_file)


def test_redacts_secrets() -> None:
    trace_file = _local_trace_file()
    tracer = JsonlTracer(output_path=trace_file)
    tracer.log_event(
        trace_id="trace_redact",
        run_id="run_redact",
        event_type="agent_start",
        input_data={
            "api_key": "secret-123",
            "headers": {"Authorization": "Bearer abc.def.ghi"},
            "to_number": "+14155550123",
        },
    )

    row = _read_jsonl(trace_file)[0]
    payload = row["input"]
    assert payload["api_key"] == "<redacted>"
    assert payload["headers"]["Authorization"] == "<redacted>"
    assert payload["to_number"] == "<redacted>"
    _cleanup(trace_file)


def test_tracing_failure_does_not_crash(monkeypatch) -> None:
    trace_file = _local_trace_file()
    tracer = JsonlTracer(output_path=trace_file)

    def _boom(*args, **kwargs):  # noqa: ANN001, ANN002
        raise OSError("disk full")

    monkeypatch.setattr(tracer, "_append_jsonl", _boom)

    tracer.log_event(trace_id="trace_fail", run_id="run_fail", event_type="agent_start")
    tracer.log_tool_start(trace_id="trace_fail", tool_name="send_email")
    _cleanup(trace_file)
