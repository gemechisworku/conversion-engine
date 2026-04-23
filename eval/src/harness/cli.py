"""CLI: doctor, run (full / smoke / both)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from harness.config import BaselineSettings
from harness.env_setup import setup_tau2_environment

app = typer.Typer(no_args_is_help=True, help="conversion-engine Act I harness (τ2-bench wrapper)")
console = Console()


def _load_config(path: Path) -> BaselineSettings:
    return BaselineSettings.from_yaml(path)


def _openrouter_only_env_hints(settings: BaselineSettings) -> None:
    """Warn when .env looks OpenRouter-only but a placeholder OpenAI key can break LiteLLM."""
    uses_or = settings.agent_llm.startswith("openrouter/") and settings.user_llm.startswith(
        "openrouter/"
    )
    if not uses_or:
        return
    oai = os.getenv("OPENAI_API_KEY") or ""
    bad = (
        not oai.strip()
        or "your_key" in oai.lower()
        or "<your" in oai.lower()
        or oai.strip() in ("sk-", "sk-test", "test")
    )
    if oai and bad:
        console.print(
            "[yellow]Tip (OpenRouter-only):[/yellow] OPENAI_API_KEY looks like a placeholder. "
            "Comment it out in tau2-bench/.env — a bad OpenAI key can trigger "
            "litellm.AuthenticationError (OpenAI) even when models are openrouter/…"
        )
    elif oai and not bad:
        console.print(
            "[dim]OPENAI_API_KEY is set (non-placeholder). If you use only OpenRouter models, "
            "you usually do not need it; remove it if you see spurious OpenAI auth errors.[/dim]"
        )




@app.command()
def doctor(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to baseline.yaml (default: harness/config/baseline.yaml)",
    ),
) -> None:
    """Check tau2 data dir, API env, task id file, and optional Langfuse keys."""
    harness_root = Path(__file__).resolve().parents[2]
    cfg_path = config or harness_root / "config" / "baseline.yaml"
    if not cfg_path.is_file():
        console.print(f"[red]Missing config:[/red] {cfg_path}")
        raise typer.Exit(code=1)
    settings = _load_config(cfg_path)
    setup_tau2_environment(tau2_root=settings.tau2_root)

    data_dir = settings.tau2_root / "data"
    console.print(f"TAU2_DATA_DIR => [cyan]{data_dir}[/cyan] ({'ok' if data_dir.is_dir() else 'MISSING'})")

    env_path = settings.tau2_root / ".env"
    console.print(f"tau2 .env: [cyan]{env_path}[/cyan] ({'found' if env_path.is_file() else 'missing'})")

    if not settings.dev_task_ids_path.is_file():
        console.print(f"[red]dev_task_ids file missing:[/red] {settings.dev_task_ids_path}")
        raise typer.Exit(code=1)
    from harness.config import load_task_id_list

    ids = load_task_id_list(settings.dev_task_ids_path)
    console.print(f"dev_task_ids: [green]{len(ids)}[/green] tasks")

    if os.getenv("OPENROUTER_API_KEY"):
        console.print("OPENROUTER_API_KEY: [green]set[/green]")
    else:
        console.print("OPENROUTER_API_KEY: [yellow]unset[/yellow] (required for OpenRouter models)")

    _openrouter_only_env_hints(settings)
    if settings.heldout_task_ids_path is not None:
        hp = settings.heldout_task_ids_path
        if hp.is_file():
            from harness.split_checks import assert_disjoint_or_raise

            hid = load_task_id_list(hp)
            console.print(f"heldout_task_ids: [green]{len(hid)}[/green] ({hp.name})")
            if len(hid) != settings.expected_heldout_count:
                console.print(
                    f"[yellow]held-out count {len(hid)} != expected_heldout_count "
                    f"({settings.expected_heldout_count})[/yellow]"
                )
            try:
                assert_disjoint_or_raise(ids, hid, context="dev vs held-out")
                console.print("dev / held-out overlap: [green]none (ok)[/green]")
            except ValueError as e:
                console.print(f"[red]{e}[/red]")
                raise typer.Exit(code=1) from e
        else:
            console.print(f"[yellow]heldout_task_ids_path set but file missing:[/yellow] {hp}")

    if (
        settings.evaluation_type == "all"
        and settings.domain == "retail"
        and not settings.nl_assertions_llm
    ):
        console.print(
            "[yellow]Tip:[/yellow] retail tasks use NL_ASSERTION. With evaluation_type=all, "
            "the NL judge defaults to OpenAI (needs OPENAI_API_KEY). "
            "Set [bold]nl_assertions_llm[/bold] in baseline.yaml to an openrouter/… model, "
            "or use evaluation_type: all_ignore_basis (skips NL LLM; different scores)."
        )

    if settings.langfuse.enabled:
        pk, sk = os.getenv("LANGFUSE_PUBLIC_KEY"), os.getenv("LANGFUSE_SECRET_KEY")
        if pk and sk:
            console.print("Langfuse keys: [green]set[/green]")
        else:
            console.print("[red]Langfuse enabled but LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY missing[/red]")
            raise typer.Exit(code=1)
    else:
        console.print("Langfuse: [dim]disabled in baseline.yaml[/dim]")

    try:
        console.print(
            "[dim]Importing tau2 (LiteLLM, pandas, …) — first import after sync can take 30–120s on Windows…[/dim]"
        )
        import tau2  # noqa: F401

        console.print("import tau2: [green]ok[/green]")
    except Exception as e:
        console.print(f"[red]import tau2 failed:[/red] {e}")
        raise typer.Exit(code=1)

    from tau2.runner.helpers import get_tasks

    console.print(f"[dim]Loading one task from domain [bold]{settings.domain}[/bold]…[/dim]")
    get_tasks(
        task_set_name=settings.domain,
        task_split_name=settings.task_split_name,
        task_ids=ids[:1],
    )
    console.print("get_tasks (1 id): [green]ok[/green]")
    console.print("[bold green]doctor: all checks passed[/bold green]")


@app.command()
def run(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to baseline.yaml",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help=(
            "Skip task×trial pairs already recorded in trace_log_summary.jsonl for this run's "
            "experiment_id (same baseline experiment_name + slice). Requires trace_summary_log_enabled."
        ),
    ),
    mode: str = typer.Option(
        "full",
        "--mode",
        "-m",
        help=(
            "full|dev — dev slice × num_trials; smoke — 3 tasks×1; both — dev then smoke; "
            "heldout_prepare — validate held-out ids + manifest (no sims); "
            "heldout_run — held-out × num_trials (needs HARNESS_HELDOUT_RUN=1)"
        ),
    ),
) -> None:
    """Run τ-bench baseline, append trace_log.jsonl, score_log.json, and Langfuse traces."""
    valid = {
        "full",
        "dev",
        "smoke",
        "both",
        "heldout_prepare",
        "heldout_run",
    }
    if mode not in valid:
        console.print(f"[red]--mode must be one of: {', '.join(sorted(valid))}[/red]")
        raise typer.Exit(code=1)
    settings = _load_config(config.resolve())
    setup_tau2_environment(tau2_root=settings.tau2_root)

    if settings.langfuse.enabled and mode != "heldout_prepare":
        if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
            console.print(
                "[red]langfuse.enabled is true but LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are missing.[/red]"
            )
            raise typer.Exit(code=1)

    from harness.runner import run_from_settings

    if resume and mode != "heldout_prepare":
        console.print(
            "[cyan]Resume:[/cyan] will reuse previous [bold]eval_run_index[/bold] and skip "
            f"task×trials already in [bold]{settings.trace_summary_log_filename}[/bold] for that index."
        )

    try:
        manifest_path = run_from_settings(settings, mode=mode, resume=resume)
        if manifest_path is not None:
            console.print(
                f"[bold green]heldout_prepare complete.[/bold green] Manifest: {manifest_path}"
            )
    finally:
        if settings.langfuse.enabled:
            try:
                from langfuse import get_client

                get_client().shutdown()
            except Exception:
                pass

    if mode != "heldout_prepare":
        console.print(
            f"[bold green]Done.[/bold green] Traces: {settings.output_dir / settings.trace_log_filename} | "
            f"Scores: {settings.output_dir / settings.score_log_filename}"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
