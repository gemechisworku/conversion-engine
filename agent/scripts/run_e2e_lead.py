"""End-to-end CLI: process_lead, advance outreach stages, optional Resend send, optional inbound reply."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.config.logging import configure_logging
from agent.config.settings import get_settings
from agent.main import build_email_service, build_enrichment_services, build_orchestration_runtime, build_state_repo
from agent.services.orchestration.outreach_pipeline import build_first_touch_outreach_request_async
from agent.services.orchestration.schemas import LeadAdvanceRequest, LeadProcessRequest, LeadReplyRequest


def _ensure_live_side_effects_policy() -> None:
    settings = get_settings()
    if settings.challenge_mode and not settings.sink_routing_enabled:
        raise SystemExit(
            "Live send is blocked: CHALLENGE_MODE=true and SINK_ROUTING_ENABLED=false. "
            "Set SINK_ROUTING_ENABLED=true or CHALLENGE_MODE=false, or omit --send-email."
        )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Run conversion-engine end-to-end: process_lead, advance to awaiting_reply, "
            "optional first-touch email via Resend, optional handle_reply."
        )
    )
    p.add_argument("--company-id", required=True, help="Stable company id (enrichment dataset key).")
    p.add_argument("--company-name", default=None, help="Display name (defaults to --company-id).")
    p.add_argument("--company-domain", default="", help="Corporate domain without scheme.")
    p.add_argument(
        "--to-email",
        default="",
        help="Recipient for first-touch email when --send-email is set.",
    )
    p.add_argument(
        "--send-email",
        action="store_true",
        help="Send one Resend email after stages (requires RESEND_* env and live policy).",
    )
    p.add_argument(
        "--no-reply",
        action="store_true",
        help="Skip handle_reply (stops after advances / optional email).",
    )
    p.add_argument(
        "--reply-channel",
        default="email",
        help="Channel for handle_reply (default: email for LLM reply path). Use sms for SMS-only tests.",
    )
    p.add_argument(
        "--reply-subject",
        default="Re: Tenacious",
        help="Inbound email subject when --reply-channel is email.",
    )
    p.add_argument(
        "--reply-content",
        default="Yes, interested. Can we schedule a 15-minute call next week?",
        help="Inbound message body for handle_reply.",
    )
    p.add_argument("--prospect-email", default="", help="Optional from_email on reply request.")
    p.add_argument("--from-number", default="", help="Optional from_number on reply request (e.g. E.164).")
    p.add_argument("--idempotency-prefix", default=None, help="Prefix for idempotency keys (default: random).")
    return p


async def _run(args: argparse.Namespace) -> int:
    configure_logging()
    if args.send_email:
        if not args.to_email.strip():
            raise SystemExit("--send-email requires --to-email.")
        _ensure_live_side_effects_policy()

    prefix = args.idempotency_prefix or f"e2e_{uuid4().hex[:12]}"
    company_name = args.company_name or args.company_id
    runtime = build_orchestration_runtime()
    repo = build_state_repo()
    email_service = build_email_service() if args.send_email else None

    out: dict = {"timings_ms": {}, "steps": []}
    t0 = perf_counter()

    process = await runtime.process_lead(
        LeadProcessRequest(
            idempotency_key=f"{prefix}_process",
            company_id=args.company_id,
            metadata={
                "company_name": company_name,
                "company_domain": args.company_domain or "",
                "initiated_by": "run_e2e_lead_cli",
            },
        )
    )
    out["timings_ms"]["process_lead"] = round((perf_counter() - t0) * 1000, 2)
    out["steps"].append({"name": "process_lead", "envelope": process.model_dump(mode="json")})
    if process.status != "accepted":
        print(json.dumps(out, indent=2))
        return 1

    lead_id = process.data["lead_id"]
    out["lead_id"] = lead_id

    advances: list[tuple[str, str]] = [
        ("brief_ready", "drafting"),
        ("drafting", "in_review"),
        ("in_review", "queued_to_send"),
        ("queued_to_send", "awaiting_reply"),
    ]
    for index, (from_state, to_state) in enumerate(advances, start=1):
        t_adv = perf_counter()
        adv = await runtime.advance_state(
            LeadAdvanceRequest(
                idempotency_key=f"{prefix}_advance_{index}",
                lead_id=lead_id,
                from_state=from_state,
                to_state=to_state,
                reason="e2e_cli_outreach_stages",
            )
        )
        out["timings_ms"][f"advance_{from_state}_{to_state}"] = round((perf_counter() - t_adv) * 1000, 2)
        out["steps"].append({"name": f"advance_{index}", "envelope": adv.model_dump(mode="json")})
        if adv.status != "success":
            print(json.dumps(out, indent=2))
            return 1

    if args.send_email and email_service is not None:
        briefs = repo.get_briefs(lead_id=lead_id)
        trace_send = f"trace_e2e_email_{uuid4().hex[:10]}"
        t_send = perf_counter()
        settings = get_settings()
        _, _, _, _, _, _, llm = build_enrichment_services()
        req = await build_first_touch_outreach_request_async(
            settings=settings,
            llm=llm,
            lead_id=lead_id,
            to_email=args.to_email.strip(),
            company_name=company_name,
            trace_id=trace_send,
            idempotency_key=f"{prefix}_first_email",
            briefs=briefs,
        )
        send_result = await email_service.send_email(req)
        out["timings_ms"]["send_email"] = round((perf_counter() - t_send) * 1000, 2)
        out["steps"].append({"name": "send_email", "result": send_result.model_dump(mode="json")})
        if not send_result.accepted:
            print(json.dumps(out, indent=2))
            return 1
        repo.append_message(
            lead_id=lead_id,
            channel="email",
            message_id=f"resend_sent_{prefix}",
            direction="outbound",
            content=req.text_body or "",
            metadata={
                "subject": req.subject,
                "provider": "resend",
                "idempotency_key": req.idempotency_key,
            },
        )
    else:
        out["steps"].append({"name": "send_email", "skipped": True})

    if not args.no_reply:
        t_reply = perf_counter()
        reply = await runtime.handle_reply(
            LeadReplyRequest(
                idempotency_key=f"{prefix}_reply",
                lead_id=lead_id,
                channel=args.reply_channel,
                message_id=f"e2e_reply_{prefix}",
                content=args.reply_content,
                subject=args.reply_subject if args.reply_channel.lower() == "email" else None,
                from_email=args.prospect_email or None,
                from_number=args.from_number or None,
                company_name=company_name,
                company_domain=args.company_domain or None,
            )
        )
        out["timings_ms"]["handle_reply"] = round((perf_counter() - t_reply) * 1000, 2)
        out["steps"].append({"name": "handle_reply", "envelope": reply.model_dump(mode="json")})
        if reply.status != "accepted":
            print(json.dumps(out, indent=2))
            return 1
    else:
        out["steps"].append({"name": "handle_reply", "skipped": True})

    state = runtime.get_state(lead_id=lead_id)
    out["final_state"] = state.model_dump(mode="json")
    print(json.dumps(out, indent=2))
    return 0


def main() -> None:
    args = _build_parser().parse_args()
    code = asyncio.run(_run(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
