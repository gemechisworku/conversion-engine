from types import SimpleNamespace

from harness.trace_summary import (
    SUMMARY_SCHEMA_VERSION,
    build_trace_summary_record,
    instruction_preview_from_task,
    message_count_from_sim,
    reward_value,
    termination_reason_str,
)


def test_instruction_preview_truncates():
    task = SimpleNamespace(
        user_scenario=SimpleNamespace(
            instructions="hello\nworld\n" + ("x" * 600),
        )
    )
    out = instruction_preview_from_task(task, max_chars=20)
    assert out.endswith("...")
    assert len(out) == 20


def test_message_count_from_sim():
    sim = SimpleNamespace(get_messages=lambda: [1, 2, 3])
    assert message_count_from_sim(sim) == 3
    sim_bad = SimpleNamespace(get_messages=lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert message_count_from_sim(sim_bad) == 0


def test_reward_and_termination():
    sim = SimpleNamespace(
        reward_info=SimpleNamespace(reward="0.5"),
        termination_reason=SimpleNamespace(value="max_steps"),
    )
    assert reward_value(sim) == 0.5
    assert termination_reason_str(sim) == "max_steps"


def test_build_trace_summary_record_shape():
    row = build_trace_summary_record(
        eval_run_index=3,
        experiment_id="exp-1",
        slice_name="dev",
        domain="retail",
        task_id="t1",
        trial_index=0,
        run_id="run-1",
        wall_time_seconds=12.3,
        cost_usd=0.01,
        success=True,
        reward=1.0,
        termination_reason="user_stop",
        message_count=4,
        instruction_preview="hi",
        agent_llm="openrouter/a",
        user_llm="openrouter/b",
        tau2_bench_git_sha="abcdef123456",
        harness_git_sha="9999999",
        langfuse_trace_id="abc",
        recorded_at="2026-01-01T00:00:00+00:00",
    )
    assert row["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert row["eval_run_index"] == 3
    assert row["tau2_bench_git_sha"] == "abcdef1"
    assert row["harness_git_sha"] == "9999999"
    assert row["langfuse_trace_id"] == "abc"

    row2 = build_trace_summary_record(
        eval_run_index=1,
        experiment_id="e",
        slice_name="dev",
        domain="d",
        task_id="t",
        trial_index=0,
        run_id="r",
        wall_time_seconds=1.0,
        cost_usd=0.0,
        success=False,
        reward=None,
        termination_reason="",
        message_count=0,
        instruction_preview="",
        agent_llm="a",
        user_llm="b",
        tau2_bench_git_sha="short",
        harness_git_sha="x",
        langfuse_trace_id=None,
        recorded_at="2026-01-02T00:00:00+00:00",
    )
    assert "langfuse_trace_id" not in row2
