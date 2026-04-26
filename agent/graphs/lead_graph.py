"""Lead intake orchestration entry."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any

from agent.config.settings import Settings
from agent.graphs.state import LeadGraphState
from agent.graphs.transitions import validate_lead_transition
from agent.services.enrichment.ai_maturity import score_ai_maturity_with_llm
from agent.services.enrichment.hiring_brief import build_hiring_signal_brief_with_llm
from agent.services.enrichment.icp_classifier import classify_icp, classify_icp_with_care
from agent.services.enrichment.schemas import EnrichmentArtifact
from agent.services.observability.langfuse_llm import langfuse_workflow_span
from agent.tools.enrichment_tools import enrich_company

ENRICHMENT_PROGRESS_STEPS: list[tuple[str, str]] = [
    ("enrichment.resolve_record", "Resolve source company record"),
    ("enrichment.crunchbase", "Collect Crunchbase profile"),
    ("enrichment.job_posts", "Collect public job-post signals"),
    ("enrichment.layoffs", "Collect layoff signals"),
    ("enrichment.leadership", "Collect leadership-change signals"),
    ("enrichment.merge", "Merge enrichment sources"),
    ("enrichment.ai_maturity", "Score AI maturity"),
    ("enrichment.icp_classification", "Classify ICP segment"),
    ("enrichment.competitor_gap", "Build competitor gap brief"),
    ("enrichment.hiring_signal_brief", "Build hiring signal brief"),
    ("enrichment.persist", "Persist briefs and evidence"),
]
ENRICHMENT_PROGRESS_LABELS = {step: label for step, label in ENRICHMENT_PROGRESS_STEPS}


def _lf_span(settings: Settings | None, *, trace_id: str, lead_id: str, name: str):
    if isinstance(settings, Settings) and trace_id.strip():
        return langfuse_workflow_span(settings, trace_id=trace_id, lead_id=lead_id, name=name)
    return nullcontext()


def _updated_enrichment_actions(
    *,
    existing_actions: list[dict[str, Any]] | Any,
    step: str,
    status: str,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC).isoformat()
    statuses: dict[str, str] = {}
    started_at: dict[str, str] = {}
    completed_at: dict[str, str] = {}
    if isinstance(existing_actions, list):
        for item in existing_actions:
            if not isinstance(item, dict):
                continue
            action_type = str(item.get("action_type") or "").strip()
            existing_status = str(item.get("status") or "").strip().lower()
            if action_type in ENRICHMENT_PROGRESS_LABELS and existing_status in {"pending", "running", "done", "failed"}:
                statuses[action_type] = existing_status
                started = item.get("started_at")
                completed = item.get("completed_at")
                if isinstance(started, str) and started.strip():
                    started_at[action_type] = started
                if isinstance(completed, str) and completed.strip():
                    completed_at[action_type] = completed
    for action_type in ENRICHMENT_PROGRESS_LABELS:
        statuses.setdefault(action_type, "pending")
    if step in statuses:
        previous = statuses[step]
        statuses[step] = status
        if status == "running":
            if previous != "running":
                started_at[step] = now
            completed_at.pop(step, None)
        elif status in {"done", "failed"}:
            started_at.setdefault(step, now)
            completed_at[step] = now
        elif status == "pending":
            started_at.pop(step, None)
            completed_at.pop(step, None)
    if status == "running":
        for action_type, existing_status in list(statuses.items()):
            if action_type != step and existing_status == "running":
                statuses[action_type] = "pending"
                started_at.pop(action_type, None)
                completed_at.pop(action_type, None)
    return [
        {
            "action_type": action_type,
            "label": ENRICHMENT_PROGRESS_LABELS[action_type],
            "status": statuses[action_type],
            "started_at": started_at.get(action_type),
            "completed_at": completed_at.get(action_type),
        }
        for action_type, _ in ENRICHMENT_PROGRESS_STEPS
    ]


def _upsert_enrichment_progress(
    *,
    state_repo: Any,
    lead_id: str,
    step: str,
    status: str,
    objective: str,
) -> None:
    session = state_repo.get_session_state(lead_id=lead_id)
    if session is None:
        return
    actions = _updated_enrichment_actions(
        existing_actions=session.get("pending_actions"),
        step=step,
        status=status,
    )
    state_repo.upsert_session_state(
        lead_id=lead_id,
        payload={
            **session,
            "current_objective": objective,
            "pending_actions": actions,
        },
    )


async def run_lead_intake(
    *,
    state: LeadGraphState,
    company_name: str,
    company_domain: str,
    services: dict,
) -> tuple[LeadGraphState, EnrichmentArtifact]:
    # Implements: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6
    # Workflow: lead_intake_and_enrichment.md
    # Schema: session_state.md
    # API: orchestration_api.md
    if not state.company_id:
        raise ValueError("company_id is required for lead intake enrichment.")
    settings_obj = services.get("settings")
    llm_client = services.get("llm")
    raw_trace = services.get("trace_id")
    trace_hint = str(raw_trace).strip() if raw_trace is not None else ""
    trace_for_edges = trace_hint or f"lead_intake:{state.lead_id}"
    lf_settings = settings_obj if isinstance(settings_obj, Settings) else None
    lf_trace = trace_hint or None
    state_repo = services.get("state_repo")

    async def mark_progress(step: str, status: str, objective: str) -> None:
        if state_repo is None:
            return
        _upsert_enrichment_progress(
            state_repo=state_repo,
            lead_id=state.lead_id,
            step=step,
            status=status,
            objective=objective,
        )

    async def run_progressed(step: str, objective: str, callback):
        await mark_progress(step, "running", objective)
        try:
            result = await callback()
        except Exception:
            await mark_progress(step, "failed", objective)
            raise
        await mark_progress(step, "done", objective)
        return result

    artifact = await enrich_company(
        company_id=state.company_id,
        company_name=company_name,
        company_domain=company_domain,
        crunchbase=services["crunchbase"],
        jobs=services["jobs"],
        layoffs=services["layoffs"],
        leadership=services["leadership"],
        merger=services["merger"],
        lf_settings=lf_settings,
        lf_trace_id=lf_trace,
        lf_lead_id=state.lead_id,
        progress_cb=mark_progress,
    )
    async def _score():
        with _lf_span(
            lf_settings,
            trace_id=trace_hint,
            lead_id=state.lead_id,
            name="enrichment.ai_maturity",
        ):
            return await score_ai_maturity_with_llm(
                company_id=state.company_id,
                artifact=artifact,
                llm=llm_client,
            )

    ai_maturity = await run_progressed("enrichment.ai_maturity", "Score AI maturity", _score)

    async def _classify():
        with _lf_span(
            lf_settings,
            trace_id=trace_hint,
            lead_id=state.lead_id,
            name="enrichment.icp_classification",
        ):
            if isinstance(settings_obj, Settings) and llm_client is not None:
                return await classify_icp_with_care(
                    artifact=artifact,
                    ai_maturity=ai_maturity,
                    llm=llm_client,
                    settings=settings_obj,
                    trace_id=trace_hint or None,
                    lead_id=state.lead_id,
                )
            return classify_icp(artifact=artifact, ai_maturity=ai_maturity)

    classification = await run_progressed("enrichment.icp_classification", "Classify ICP segment", _classify)

    async def _gap():
        with _lf_span(
            lf_settings,
            trace_id=trace_hint,
            lead_id=state.lead_id,
            name="enrichment.competitor_gap_brief",
        ):
            return await services["competitor_gap"].build_brief(
                lead_id=state.lead_id,
                company_id=state.company_id,
                artifact=artifact,
                ai_maturity=ai_maturity,
            )

    gap_brief = await run_progressed("enrichment.competitor_gap", "Build competitor gap brief", _gap)

    async def _hiring():
        with _lf_span(
            lf_settings,
            trace_id=trace_hint,
            lead_id=state.lead_id,
            name="enrichment.hiring_signal_brief",
        ):
            return await build_hiring_signal_brief_with_llm(
                lead_id=state.lead_id,
                company_id=state.company_id,
                artifact=artifact,
                ai_maturity=ai_maturity,
                classification=classification,
                llm=llm_client,
            )

    hiring_brief = await run_progressed("enrichment.hiring_signal_brief", "Build hiring signal brief", _hiring)
    if state_repo is not None:
        await mark_progress("enrichment.persist", "running", "Persist briefs and evidence")
        state_repo.cache_enrichment(
            lead_id=state.lead_id,
            company_id=state.company_id,
            artifact=artifact.model_dump(mode="json"),
        )
        state_repo.upsert_briefs(
            lead_id=state.lead_id,
            hiring_signal_brief=hiring_brief.model_dump(mode="json"),
            competitor_gap_brief=gap_brief.model_dump(mode="json"),
            ai_maturity_score=ai_maturity.model_dump(mode="json"),
        )
        repo = state_repo
        repo.append_evidence_edge(
            lead_id=state.lead_id,
            trace_id=trace_for_edges,
            edge_type="brief.hiring_signal",
            brief_id=hiring_brief.brief_id,
            payload={"brief_id": hiring_brief.brief_id, "kind": "hiring_signal_brief"},
        )
        repo.append_evidence_edge(
            lead_id=state.lead_id,
            trace_id=trace_for_edges,
            edge_type="brief.competitor_gap",
            brief_id=gap_brief.gap_brief_id,
            payload={"gap_brief_id": gap_brief.gap_brief_id, "kind": "competitor_gap_brief"},
        )
        repo.append_evidence_edge(
            lead_id=state.lead_id,
            trace_id=trace_for_edges,
            edge_type="score.ai_maturity",
            brief_id=None,
            source_ref=ai_maturity.score_id,
            payload={"score_id": ai_maturity.score_id, "kind": "ai_maturity_score"},
        )
        writer = services.get("artifact_writer")
        if writer is not None:
            writer.write_lead_briefs(
                lead_id=state.lead_id,
                hiring_signal_brief=hiring_brief.model_dump(mode="json"),
                competitor_gap_brief=gap_brief.model_dump(mode="json"),
                ai_maturity_score=ai_maturity.model_dump(mode="json"),
                enrichment_artifact=artifact.model_dump(mode="json"),
            )
        await mark_progress("enrichment.persist", "done", "Persist briefs and evidence")
    validate_lead_transition(from_state=state.current_stage, to_state="brief_ready")
    updated_state = state.model_copy(
        update={
            "current_stage": "brief_ready",
            "enrichment_refs": [artifact.company_id],
            "brief_refs": [hiring_brief.brief_id, gap_brief.gap_brief_id, ai_maturity.score_id],
            "next_best_action": "draft",
            "updated_at": hiring_brief.generated_at,
        }
    )
    return updated_state, artifact
