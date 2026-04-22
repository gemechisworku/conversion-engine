"""Load baseline YAML into a typed settings object."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from harness.paths import resolve_path


def _coerce_bool(v: Any) -> bool:
    """YAML-friendly bool (rejects arbitrary truthy strings like ``enabled``)."""
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return bool(int(v))
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return False


class LangfuseSettings(BaseModel):
    enabled: bool = False
    host: Optional[str] = Field(
        default=None,
        description="Override LANGFUSE_HOST / LANGFUSE_BASE_URL if set in YAML",
    )


class BaselineSettings(BaseModel):
    experiment_name: str
    domain: str = "retail"
    task_split_name: str = "base"
    dev_task_ids_path: Path
    tau2_root: Path = Field(
        default=Path("../tau2-bench"),
        description="Path to tau2-bench checkout (contains data/ and .env); resolved in from_yaml",
    )
    num_trials: int = 5
    max_concurrency: int = 3
    max_steps: int = 200
    max_errors: int = 10
    evaluation_type: str = "all"
    # When set, overrides tau2.config.DEFAULT_LLM_NL_ASSERTIONS so NL-assertion judging
    # uses this model (e.g. same OpenRouter slug as the agent). Required for evaluation_type
    # ``all`` on retail if you have no OPENAI_API_KEY.
    nl_assertions_llm: Optional[str] = None
    nl_assertions_llm_args: Optional[dict[str, Any]] = None
    agent_implementation: str = "llm_agent"
    user_implementation: str = "user_simulator"
    agent_llm: str
    user_llm: str
    agent_llm_args: dict[str, Any] = Field(default_factory=dict)
    user_llm_args: dict[str, Any] = Field(default_factory=dict)
    output_dir: Path = Field(default_factory=lambda: Path("../outputs"))
    trace_log_filename: str = "trace_log.jsonl"
    score_log_filename: str = "score_log.json"
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    notes: str = ""
    seed: int = 300
    log_level: str = "ERROR"
    max_retries: int = 3
    retry_delay: float = 1.0
    # Retries inside each simulation when OpenRouter / upstream returns 429 (esp. :free models).
    openrouter_rate_limit_attempts: int = 12
    openrouter_rate_limit_backoff_base_seconds: float = 2.0
    openrouter_rate_limit_backoff_max_seconds: float = 120.0

    @classmethod
    def from_yaml(cls, path: Path) -> BaselineSettings:
        path = path.resolve()
        base = path.parent
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid YAML (expected mapping): {path}")

        raw.setdefault("tau2_root", "../../tau2-bench")
        raw["tau2_root"] = resolve_path(raw["tau2_root"], base=base)
        raw["dev_task_ids_path"] = resolve_path(raw["dev_task_ids_path"], base=base)
        raw["output_dir"] = resolve_path(raw.get("output_dir", "../outputs"), base=base)

        lf = raw.get("langfuse") or {}
        raw["langfuse"] = LangfuseSettings(
            enabled=_coerce_bool(lf.get("enabled", False)),
            host=lf.get("host"),
        )

        return cls.model_validate(raw)


def load_task_id_list(path: Path) -> list[str]:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array of task ids: {path}")
    return [str(x) for x in data]
