"""CLI: run lead intake through OrchestrationRuntime (enrichment LangGraph + optional HubSpot)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

# Repo root on sys.path (same pattern as live_smoke.py)
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.config.logging import configure_logging
from agent.main import build_orchestration_runtime
from agent.services.orchestration.schemas import LeadProcessRequest


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run the conversion-engine orchestrator: process_lead (enrich -> CRM sync -> session state).",
    )
    p.add_argument("--company-id", required=True, help="Stable company identifier (matches enrichment dataset keys).")
    p.add_argument(
        "--company-name",
        default=None,
        help="Display name for enrichment matching (defaults to --company-id).",
    )
    p.add_argument(
        "--company-domain",
        default="",
        help="Corporate website domain without scheme (e.g. acme.ai).",
    )
    p.add_argument(
        "--idempotency-key",
        default=None,
        help="Idempotency key for HubSpot writes (default: auto-generated).",
    )
    return p


async def _run(args: argparse.Namespace) -> int:
    configure_logging()
    runtime = build_orchestration_runtime()
    idem = args.idempotency_key or f"cli_process_{uuid4().hex[:12]}"
    company_name = args.company_name or args.company_id
    request = LeadProcessRequest(
        idempotency_key=idem,
        company_id=args.company_id,
        metadata={
            "company_name": company_name,
            "company_domain": args.company_domain or "",
            "initiated_by": "run_orchestrator_cli",
        },
    )
    envelope = await runtime.process_lead(request)
    print(json.dumps(envelope.model_dump(mode="json"), indent=2))
    return 0 if envelope.status == "accepted" else 1


def main() -> None:
    args = _build_parser().parse_args()
    code = asyncio.run(_run(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
