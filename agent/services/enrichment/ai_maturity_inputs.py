"""Collect normalized AI-maturity input signals from enrichment artifacts."""

from __future__ import annotations

from typing import Any

from agent.services.enrichment.schemas import EnrichmentArtifact, SignalSnapshot, SourceRef

INPUT_AI_ROLES = "ai_adjacent_open_roles"
INPUT_AI_LEADERSHIP = "named_ai_ml_leadership"
INPUT_GITHUB = "github_org_activity"
INPUT_EXEC_COMMENTARY = "executive_commentary"
INPUT_STACK = "modern_data_ml_stack"
INPUT_STRATEGIC_COMMS = "strategic_communications"


def collect_ai_maturity_inputs(*, artifact: EnrichmentArtifact) -> dict[str, SignalSnapshot]:
    # Implements: FR-3
    # Workflow: lead_intake_and_enrichment.md
    # Schema: ai_maturity_score.md
    # API: scoring_api.md
    jobs = artifact.signals.get("job_posts")
    leadership = artifact.signals.get("leadership_changes")
    crunchbase = artifact.signals.get("crunchbase")
    tech_stack = artifact.signals.get("tech_stack")
    jobs_summary = _summary(jobs)
    leadership_summary = _summary(leadership)
    crunchbase_summary = _summary(crunchbase)
    stack_summary = _summary(tech_stack)

    ai_roles = int(jobs_summary.get("ai_adjacent_role_count") or 0)
    role_name = str(leadership_summary.get("role_name") or "").strip()
    leadership_entries = _as_list(crunchbase_summary.get("leadership_hire"))
    social_links = _as_list(crunchbase_summary.get("social_media_links"))
    news = _as_list(crunchbase_summary.get("news"))
    technologies = [str(item).strip() for item in _as_list(stack_summary.get("technologies")) if str(item).strip()]
    overview = crunchbase_summary.get("overview_highlights")
    full_description = str(crunchbase_summary.get("full_description") or "").strip()
    num_news = _as_int(crunchbase_summary.get("num_news"))

    has_ai_leader = _is_ai_leadership_role(role_name)
    if not has_ai_leader:
        for entry in leadership_entries:
            if not isinstance(entry, dict):
                continue
            candidate_role = str(entry.get("role_name") or entry.get("title") or entry.get("role") or "").strip()
            if _is_ai_leadership_role(candidate_role):
                role_name = candidate_role
                has_ai_leader = True
                break

    github_links = [str(link).strip() for link in social_links if "github.com/" in str(link).lower()]
    github_orgs = [_github_org_from_url(link) for link in github_links]
    github_orgs = [org for org in github_orgs if org]

    commentary_hit = _has_executive_commentary(news=news, full_description=full_description)
    stack_hits = _modern_stack_hits(technologies)
    strategic_hit = num_news > 0 or bool(_as_list(overview)) or len(news) > 0

    source_crunchbase = _source_refs(crunchbase, fallback_name="crunchbase")
    source_jobs = _source_refs(jobs, fallback_name="job_posts")
    source_leadership = _source_refs(leadership, fallback_name="leadership_public")
    source_stack = _source_refs(tech_stack, fallback_name="tech_stack")

    return {
        INPUT_AI_ROLES: SignalSnapshot(
            summary={"present": ai_roles > 0, "ai_adjacent_role_count": ai_roles},
            confidence=float(jobs.confidence if jobs is not None else 0.3),
            source_refs=source_jobs,
        ),
        INPUT_AI_LEADERSHIP: SignalSnapshot(
            summary={"present": has_ai_leader, "role_name": role_name or None},
            confidence=float(leadership.confidence if leadership is not None else 0.35),
            source_refs=source_leadership,
        ),
        INPUT_GITHUB: SignalSnapshot(
            summary={
                "present": bool(github_orgs),
                "orgs": github_orgs[:3],
                "links": github_links[:3],
            },
            confidence=0.62 if github_orgs else 0.35,
            source_refs=source_crunchbase,
        ),
        INPUT_EXEC_COMMENTARY: SignalSnapshot(
            summary={"present": commentary_hit, "news_items_considered": len(news)},
            confidence=0.58 if commentary_hit else 0.32,
            source_refs=source_crunchbase,
        ),
        INPUT_STACK: SignalSnapshot(
            summary={"present": bool(stack_hits), "stack_hits": stack_hits[:6]},
            confidence=float(tech_stack.confidence if tech_stack is not None else 0.4),
            source_refs=source_stack,
        ),
        INPUT_STRATEGIC_COMMS: SignalSnapshot(
            summary={
                "present": strategic_hit,
                "num_news": num_news,
                "has_overview_highlights": bool(_as_list(overview)),
            },
            confidence=0.6 if strategic_hit else 0.3,
            source_refs=source_crunchbase,
        ),
    }


def _summary(snapshot: SignalSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return snapshot.summary if isinstance(snapshot.summary, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    text = str(value).strip()
    if not text:
        return []
    return [text]


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _source_refs(snapshot: SignalSnapshot | None, *, fallback_name: str) -> list[SourceRef]:
    if snapshot is not None and snapshot.source_refs:
        return list(snapshot.source_refs)
    return [SourceRef(source_name=fallback_name)]


def _is_ai_leadership_role(role_name: str) -> bool:
    lower = role_name.lower()
    return any(
        token in lower
        for token in (
            "chief ai",
            "chief data",
            "head of ai",
            "head of ml",
            "vp ai",
            "vp machine learning",
            "director ai",
            "director ml",
            "machine learning",
            "artificial intelligence",
        )
    )


def _github_org_from_url(url: str) -> str | None:
    lower = url.strip().lower()
    marker = "github.com/"
    if marker not in lower:
        return None
    tail = lower.split(marker, 1)[1]
    org = tail.split("/", 1)[0].strip()
    if not org or org in {"features", "topics", "about", "orgs", "users"}:
        return None
    return org


def _has_executive_commentary(*, news: list[Any], full_description: str) -> bool:
    executive_markers = ("ceo", "cto", "chief", "founder", "co-founder")
    quote_markers = ("said", "shared", "announced", "noted", "commented")
    if full_description:
        lower_desc = full_description.lower()
        if any(marker in lower_desc for marker in executive_markers) and any(marker in lower_desc for marker in quote_markers):
            return True
    for item in news:
        text = str(item).lower()
        if any(marker in text for marker in executive_markers) and any(marker in text for marker in quote_markers):
            return True
    return False


def _modern_stack_hits(technologies: list[str]) -> list[str]:
    markers = (
        "databricks",
        "snowflake",
        "dbt",
        "airflow",
        "kafka",
        "pytorch",
        "tensorflow",
        "openai",
        "vertex ai",
        "sagemaker",
        "hugging face",
    )
    hits: list[str] = []
    for item in technologies:
        lower = item.lower()
        if any(marker in lower for marker in markers):
            hits.append(item)
    return hits
