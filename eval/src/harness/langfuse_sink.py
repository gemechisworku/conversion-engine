"""Send one τ-bench simulation to Langfuse (trace + score). Langfuse Python SDK v4+."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from harness.config import LangfuseSettings

logger = logging.getLogger(__name__)


class LangfuseSink:
    """Optional Langfuse client (v4 ``get_client()``); no-op when disabled."""

    def __init__(self, settings: LangfuseSettings) -> None:
        self.enabled = settings.enabled
        self._client: Any = None
        if not self.enabled:
            return
        if settings.host:
            os.environ.setdefault("LANGFUSE_BASE_URL", settings.host)
            os.environ.setdefault("LANGFUSE_HOST", settings.host)
        self._init_client()

    def _init_client(self) -> None:
        try:
            from langfuse import get_client

            self._client = get_client()
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Langfuse is enabled but could not initialize. "
                "Install: uv sync --extra langfuse. "
                "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY "
                "(and LANGFUSE_BASE_URL / LANGFUSE_HOST for self-hosted)."
            ) from e

    def log_simulation(
        self,
        *,
        tau2_run_id: str,
        domain: str,
        task_id: str,
        trial_index: int,
        experiment_name: str,
        agent_llm: str,
        user_llm: str,
        wall_time_s: float,
        simulation_output: dict[str, Any],
    ) -> Optional[str]:
        """
        Create a Langfuse trace (root span + score) for one simulation.

        ``simulation_output`` must be the **same** dict written to ``trace_log.jsonl`` under
        ``simulation`` (already truncated when using compact mode).

        Langfuse v4 expects W3C-style **32 hex char** trace ids. τ-bench uses UUID strings,
        so we derive a valid id with ``create_trace_id(seed=tau2_run_id)`` (deterministic).

        Returns the **Langfuse** trace id (hex), or ``None`` on failure.
        """
        if not self.enabled or self._client is None:
            return None

        reward_info = simulation_output.get("reward_info") or {}
        reward = reward_info.get("reward")
        success = reward is not None and float(reward) >= 1.0

        lf_trace_id = self._client.create_trace_id(seed=tau2_run_id)

        metadata: dict[str, Any] = {
            "tau2_simulation_run_id": tau2_run_id,
            "domain": domain,
            "task_id": task_id,
            "trial_index": trial_index,
            "experiment_name": experiment_name,
            "agent_llm": agent_llm,
            "user_llm": user_llm,
            "wall_time_seconds": wall_time_s,
            "success": success,
            "reward": reward,
        }

        trace_input = {
            "tau2_simulation_run_id": tau2_run_id,
            "task_id": task_id,
            "trial_index": trial_index,
            "experiment_name": experiment_name,
        }

        from langfuse.types import TraceContext

        ctx = TraceContext(trace_id=lf_trace_id)
        span_name = f"tau2.{domain}.task_{task_id}.trial_{trial_index}"

        with self._client.start_as_current_observation(
            trace_context=ctx,
            name=span_name,
            as_type="span",
            input=trace_input,
            output=simulation_output,
            metadata=metadata,
        ):
            pass

        self._client.create_score(
            name="tau2_success",
            value=1.0 if success else 0.0,
            trace_id=lf_trace_id,
            data_type="NUMERIC",
            comment=f"reward={reward}",
        )
        self._client.flush()
        return lf_trace_id
