"""SQLite-backed runtime state repository."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from agent.services.email.rfc_ids import merge_references_header, normalize_message_id


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteStateRepository:
    # Implements: FR-14
    # Workflow: reply_handling.md
    # Schema: session_state.md
    # API: orchestration_api.md
    def __init__(self, *, db_path: str) -> None:
        self._db_path = str(Path(db_path))
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path)
        connection.execute("PRAGMA journal_mode=MEMORY")
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS lead_session_state (
                    lead_id TEXT PRIMARY KEY,
                    current_stage TEXT NOT NULL,
                    next_best_action TEXT NOT NULL,
                    current_objective TEXT NOT NULL,
                    brief_refs TEXT NOT NULL,
                    kb_refs TEXT NOT NULL,
                    pending_actions TEXT NOT NULL,
                    policy_flags TEXT NOT NULL,
                    handoff_required INTEGER NOT NULL,
                    last_compacted_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_state (
                    lead_id TEXT PRIMARY KEY,
                    conversation_state_id TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    current_channel TEXT NOT NULL,
                    last_inbound_message_id TEXT,
                    last_outbound_message_id TEXT,
                    last_customer_intent TEXT NOT NULL,
                    last_customer_sentiment TEXT NOT NULL,
                    qualification_status TEXT NOT NULL,
                    open_questions TEXT NOT NULL,
                    pending_actions TEXT NOT NULL,
                    objections TEXT NOT NULL,
                    scheduling_context TEXT NOT NULL,
                    policy_flags TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS message_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    content TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sms_consent_state (
                    lead_id TEXT PRIMARY KEY,
                    sms_allowed INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS phone_lead_map (
                    phone_number TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lead_briefs (
                    lead_id TEXT PRIMARY KEY,
                    hiring_signal_brief TEXT,
                    competitor_gap_brief TEXT,
                    ai_maturity_score TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lead_enrichment_cache (
                    lead_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    enrichment_artifact TEXT NOT NULL,
                    generated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS act2_enrichment_briefs (
                    lead_id TEXT PRIMARY KEY,
                    enrichment_brief TEXT NOT NULL,
                    compliance_brief TEXT NOT NULL,
                    news_brief TEXT NOT NULL,
                    artifact_paths TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS email_threads (
                    thread_id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    last_inbound_rfc_message_id TEXT,
                    references_header TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_email_threads_lead_id ON email_threads(lead_id);

                CREATE TABLE IF NOT EXISTS outreach_draft_state (
                    lead_id TEXT PRIMARY KEY,
                    draft_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_send_idempotency TEXT
                );

                CREATE TABLE IF NOT EXISTS orchestration_idempotency (
                    idempotency_key TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence_graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    claim_ref TEXT,
                    brief_id TEXT,
                    source_ref TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_lead_id ON evidence_graph_edges(lead_id);
                CREATE INDEX IF NOT EXISTS idx_evidence_trace_id ON evidence_graph_edges(trace_id);

                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    lead_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    company_domain TEXT,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    last_stage TEXT NOT NULL,
                    last_trace_id TEXT,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_updated_at ON pipeline_runs(updated_at);
                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_company_name ON pipeline_runs(company_name);
                """
            )

    def upsert_session_state(self, *, lead_id: str, payload: dict[str, Any]) -> None:
        row = {
            "lead_id": lead_id,
            "current_stage": payload.get("current_stage", "new_lead"),
            "next_best_action": payload.get("next_best_action", "enrich"),
            "current_objective": payload.get("current_objective", "process_lead"),
            "brief_refs": json.dumps(payload.get("brief_refs", [])),
            "kb_refs": json.dumps(payload.get("kb_refs", [])),
            "pending_actions": json.dumps(payload.get("pending_actions", [])),
            "policy_flags": json.dumps(payload.get("policy_flags", [])),
            "handoff_required": 1 if payload.get("handoff_required", False) else 0,
            "last_compacted_at": payload.get("last_compacted_at"),
            "updated_at": payload.get("updated_at") or _utc_now(),
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO lead_session_state (
                    lead_id, current_stage, next_best_action, current_objective, brief_refs, kb_refs,
                    pending_actions, policy_flags, handoff_required, last_compacted_at, updated_at
                ) VALUES (
                    :lead_id, :current_stage, :next_best_action, :current_objective, :brief_refs, :kb_refs,
                    :pending_actions, :policy_flags, :handoff_required, :last_compacted_at, :updated_at
                )
                ON CONFLICT(lead_id) DO UPDATE SET
                    current_stage=excluded.current_stage,
                    next_best_action=excluded.next_best_action,
                    current_objective=excluded.current_objective,
                    brief_refs=excluded.brief_refs,
                    kb_refs=excluded.kb_refs,
                    pending_actions=excluded.pending_actions,
                    policy_flags=excluded.policy_flags,
                    handoff_required=excluded.handoff_required,
                    last_compacted_at=excluded.last_compacted_at,
                    updated_at=excluded.updated_at
                """,
                row,
            )

    def get_session_state(self, *, lead_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM lead_session_state WHERE lead_id = ?",
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "lead_id": row["lead_id"],
            "current_stage": row["current_stage"],
            "next_best_action": row["next_best_action"],
            "current_objective": row["current_objective"],
            "brief_refs": json.loads(row["brief_refs"]),
            "kb_refs": json.loads(row["kb_refs"]),
            "pending_actions": json.loads(row["pending_actions"]),
            "policy_flags": json.loads(row["policy_flags"]),
            "handoff_required": bool(row["handoff_required"]),
            "last_compacted_at": row["last_compacted_at"],
            "updated_at": row["updated_at"],
        }

    def upsert_conversation_state(self, *, lead_id: str, payload: dict[str, Any]) -> None:
        row = {
            "lead_id": lead_id,
            "conversation_state_id": payload.get("conversation_state_id") or f"conv_{uuid4().hex[:10]}",
            "current_stage": payload.get("current_stage", "no_conversation"),
            "current_channel": payload.get("current_channel", "email"),
            "last_inbound_message_id": payload.get("last_inbound_message_id"),
            "last_outbound_message_id": payload.get("last_outbound_message_id"),
            "last_customer_intent": payload.get("last_customer_intent", "unknown"),
            "last_customer_sentiment": payload.get("last_customer_sentiment", "uncertain"),
            "qualification_status": payload.get("qualification_status", "unknown"),
            "open_questions": json.dumps(payload.get("open_questions", [])),
            "pending_actions": json.dumps(payload.get("pending_actions", [])),
            "objections": json.dumps(payload.get("objections", [])),
            "scheduling_context": json.dumps(payload.get("scheduling_context", {"booking_status": "none"})),
            "policy_flags": json.dumps(payload.get("policy_flags", [])),
            "updated_at": payload.get("updated_at") or _utc_now(),
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO conversation_state (
                    lead_id, conversation_state_id, current_stage, current_channel, last_inbound_message_id,
                    last_outbound_message_id, last_customer_intent, last_customer_sentiment, qualification_status,
                    open_questions, pending_actions, objections, scheduling_context, policy_flags, updated_at
                ) VALUES (
                    :lead_id, :conversation_state_id, :current_stage, :current_channel, :last_inbound_message_id,
                    :last_outbound_message_id, :last_customer_intent, :last_customer_sentiment, :qualification_status,
                    :open_questions, :pending_actions, :objections, :scheduling_context, :policy_flags, :updated_at
                )
                ON CONFLICT(lead_id) DO UPDATE SET
                    conversation_state_id=excluded.conversation_state_id,
                    current_stage=excluded.current_stage,
                    current_channel=excluded.current_channel,
                    last_inbound_message_id=excluded.last_inbound_message_id,
                    last_outbound_message_id=excluded.last_outbound_message_id,
                    last_customer_intent=excluded.last_customer_intent,
                    last_customer_sentiment=excluded.last_customer_sentiment,
                    qualification_status=excluded.qualification_status,
                    open_questions=excluded.open_questions,
                    pending_actions=excluded.pending_actions,
                    objections=excluded.objections,
                    scheduling_context=excluded.scheduling_context,
                    policy_flags=excluded.policy_flags,
                    updated_at=excluded.updated_at
                """,
                row,
            )

    def get_conversation_state(self, *, lead_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM conversation_state WHERE lead_id = ?", (lead_id,)).fetchone()
        if row is None:
            return None
        return {
            "lead_id": row["lead_id"],
            "conversation_state_id": row["conversation_state_id"],
            "current_stage": row["current_stage"],
            "current_channel": row["current_channel"],
            "last_inbound_message_id": row["last_inbound_message_id"],
            "last_outbound_message_id": row["last_outbound_message_id"],
            "last_customer_intent": row["last_customer_intent"],
            "last_customer_sentiment": row["last_customer_sentiment"],
            "qualification_status": row["qualification_status"],
            "open_questions": json.loads(row["open_questions"]),
            "pending_actions": json.loads(row["pending_actions"]),
            "objections": json.loads(row["objections"]),
            "scheduling_context": json.loads(row["scheduling_context"]),
            "policy_flags": json.loads(row["policy_flags"]),
            "updated_at": row["updated_at"],
        }

    def append_message(
        self,
        *,
        lead_id: str,
        channel: str,
        message_id: str,
        direction: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO message_log (lead_id, channel, message_id, direction, content, recorded_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    channel,
                    message_id,
                    direction,
                    content,
                    _utc_now(),
                    json.dumps(metadata or {}),
                ),
            )

    def list_messages(self, *, lead_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT lead_id, channel, message_id, direction, content, recorded_at, metadata
                FROM message_log
                WHERE lead_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (lead_id, limit),
            ).fetchall()
        return [
            {
                "lead_id": row["lead_id"],
                "channel": row["channel"],
                "message_id": row["message_id"],
                "direction": row["direction"],
                "content": row["content"],
                "recorded_at": row["recorded_at"],
                "metadata": json.loads(row["metadata"]),
            }
            for row in rows
        ]

    def ensure_email_thread(self, *, lead_id: str) -> str:
        """Return the newest thread_id for this lead, creating one if needed."""
        now = _utc_now()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT thread_id FROM email_threads
                WHERE lead_id = ?
                ORDER BY datetime(updated_at) DESC
                LIMIT 1
                """,
                (lead_id,),
            ).fetchone()
            if row is not None:
                return str(row["thread_id"])
            thread_id = f"emthr_{uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO email_threads (
                    thread_id, lead_id, last_inbound_rfc_message_id, references_header, created_at, updated_at
                ) VALUES (?, ?, NULL, '', ?, ?)
                """,
                (thread_id, lead_id, now, now),
            )
            return thread_id

    def get_email_thread_reply_headers(self, *, lead_id: str) -> tuple[str | None, str | None]:
        """(In-Reply-To target, References) for the next outbound, from the latest thread row."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT last_inbound_rfc_message_id, references_header
                FROM email_threads
                WHERE lead_id = ?
                ORDER BY datetime(updated_at) DESC
                LIMIT 1
                """,
                (lead_id,),
            ).fetchone()
        if row is None:
            return None, None
        last_in = row["last_inbound_rfc_message_id"]
        refs = row["references_header"] or ""
        return (last_in, refs or None)

    def email_thread_record_inbound(
        self,
        *,
        lead_id: str,
        inbound_rfc_message_id: str,
        prior_references_fragment: str | None,
    ) -> str:
        """Upsert thread for lead and merge References; set last inbound Message-Id. Returns thread_id."""
        now = _utc_now()
        mid = normalize_message_id(inbound_rfc_message_id)
        if not mid:
            return self.ensure_email_thread(lead_id=lead_id)
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT thread_id, references_header FROM email_threads
                WHERE lead_id = ?
                ORDER BY datetime(updated_at) DESC
                LIMIT 1
                """,
                (lead_id,),
            ).fetchone()
            if row is None:
                thread_id = f"emthr_{uuid4().hex[:12]}"
                merged = merge_references_header(prior_references_fragment, mid)
                conn.execute(
                    """
                    INSERT INTO email_threads (
                        thread_id, lead_id, last_inbound_rfc_message_id, references_header, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (thread_id, lead_id, mid, merged, now, now),
                )
                return thread_id
            thread_id = str(row["thread_id"])
            existing = str(row["references_header"] or "")
            merged = merge_references_header(existing, prior_references_fragment, mid)
            conn.execute(
                """
                UPDATE email_threads
                SET last_inbound_rfc_message_id = ?, references_header = ?, updated_at = ?
                WHERE thread_id = ?
                """,
                (mid, merged, now, thread_id),
            )
            return thread_id

    def set_sms_consent(self, *, lead_id: str, allowed: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sms_consent_state (lead_id, sms_allowed, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(lead_id) DO UPDATE SET
                    sms_allowed=excluded.sms_allowed,
                    updated_at=excluded.updated_at
                """,
                (lead_id, 1 if allowed else 0, _utc_now()),
            )

    def is_sms_allowed(self, *, lead_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT sms_allowed FROM sms_consent_state WHERE lead_id = ?",
                (lead_id,),
            ).fetchone()
        if row is None:
            return True
        return bool(row["sms_allowed"])

    def bind_phone(self, *, lead_id: str, phone_number: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO phone_lead_map (phone_number, lead_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(phone_number) DO UPDATE SET
                    lead_id=excluded.lead_id,
                    updated_at=excluded.updated_at
                """,
                (phone_number, lead_id, _utc_now()),
            )

    def find_lead_by_phone(self, *, phone_number: str | None) -> str | None:
        if not phone_number:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT lead_id FROM phone_lead_map WHERE phone_number = ?",
                (phone_number,),
            ).fetchone()
        return str(row["lead_id"]) if row is not None else None

    def upsert_briefs(
        self,
        *,
        lead_id: str,
        hiring_signal_brief: dict[str, Any],
        competitor_gap_brief: dict[str, Any],
        ai_maturity_score: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO lead_briefs (lead_id, hiring_signal_brief, competitor_gap_brief, ai_maturity_score, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(lead_id) DO UPDATE SET
                    hiring_signal_brief=excluded.hiring_signal_brief,
                    competitor_gap_brief=excluded.competitor_gap_brief,
                    ai_maturity_score=excluded.ai_maturity_score,
                    updated_at=excluded.updated_at
                """,
                (
                    lead_id,
                    json.dumps(hiring_signal_brief),
                    json.dumps(competitor_gap_brief),
                    json.dumps(ai_maturity_score),
                    _utc_now(),
                ),
            )

    def get_briefs(self, *, lead_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT hiring_signal_brief, competitor_gap_brief, ai_maturity_score, updated_at FROM lead_briefs WHERE lead_id = ?",
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "hiring_signal_brief": json.loads(row["hiring_signal_brief"]),
            "competitor_gap_brief": json.loads(row["competitor_gap_brief"]),
            "ai_maturity_score": json.loads(row["ai_maturity_score"]),
            "updated_at": row["updated_at"],
        }

    def cache_enrichment(self, *, lead_id: str, company_id: str, artifact: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO lead_enrichment_cache (lead_id, company_id, enrichment_artifact, generated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lead_id) DO UPDATE SET
                    company_id=excluded.company_id,
                    enrichment_artifact=excluded.enrichment_artifact,
                    generated_at=excluded.generated_at
                """,
                (lead_id, company_id, json.dumps(artifact), _utc_now()),
            )

    def get_cached_enrichment(self, *, lead_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT company_id, enrichment_artifact, generated_at FROM lead_enrichment_cache WHERE lead_id = ?",
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "company_id": row["company_id"],
            "artifact": json.loads(row["enrichment_artifact"]),
            "generated_at": row["generated_at"],
        }

    def upsert_pipeline_run_start(
        self,
        *,
        lead_id: str,
        company_id: str,
        company_name: str,
        company_domain: str | None,
        trace_id: str,
    ) -> None:
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO pipeline_runs (
                    lead_id, company_id, company_name, company_domain, run_count, last_stage, last_trace_id, started_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(lead_id) DO UPDATE SET
                    company_id=excluded.company_id,
                    company_name=excluded.company_name,
                    company_domain=excluded.company_domain,
                    run_count=pipeline_runs.run_count + 1,
                    last_stage=excluded.last_stage,
                    last_trace_id=excluded.last_trace_id,
                    started_at=excluded.started_at,
                    updated_at=excluded.updated_at
                """,
                (
                    lead_id,
                    company_id,
                    company_name.strip() or company_id,
                    (company_domain or "").strip() or None,
                    "enriching",
                    trace_id,
                    now,
                    now,
                ),
            )

    def update_pipeline_run_stage(
        self,
        *,
        lead_id: str,
        stage: str,
        trace_id: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET last_stage = ?, last_trace_id = COALESCE(?, last_trace_id), updated_at = ?
                WHERE lead_id = ?
                """,
                (stage, trace_id, _utc_now(), lead_id),
            )

    def list_pipeline_runs(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT lead_id, company_id, company_name, company_domain, run_count, last_stage, last_trace_id, started_at, updated_at
                FROM pipeline_runs
                ORDER BY datetime(updated_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "lead_id": row["lead_id"],
                "company_id": row["company_id"],
                "company_name": row["company_name"],
                "company_domain": row["company_domain"],
                "run_count": int(row["run_count"]),
                "last_stage": row["last_stage"],
                "last_trace_id": row["last_trace_id"],
                "started_at": row["started_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def upsert_act2_briefs(
        self,
        *,
        lead_id: str,
        enrichment_brief: dict[str, Any],
        compliance_brief: dict[str, Any],
        news_brief: dict[str, Any],
        artifact_paths: dict[str, str],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO act2_enrichment_briefs (
                    lead_id, enrichment_brief, compliance_brief, news_brief, artifact_paths, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(lead_id) DO UPDATE SET
                    enrichment_brief=excluded.enrichment_brief,
                    compliance_brief=excluded.compliance_brief,
                    news_brief=excluded.news_brief,
                    artifact_paths=excluded.artifact_paths,
                    updated_at=excluded.updated_at
                """,
                (
                    lead_id,
                    json.dumps(enrichment_brief),
                    json.dumps(compliance_brief),
                    json.dumps(news_brief),
                    json.dumps(artifact_paths),
                    _utc_now(),
                ),
            )

    def get_act2_briefs(self, *, lead_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT enrichment_brief, compliance_brief, news_brief, artifact_paths, updated_at
                FROM act2_enrichment_briefs
                WHERE lead_id = ?
                """,
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "enrichment_brief": json.loads(row["enrichment_brief"]),
            "compliance_brief": json.loads(row["compliance_brief"]),
            "news_brief": json.loads(row["news_brief"]),
            "artifact_paths": json.loads(row["artifact_paths"]),
            "updated_at": row["updated_at"],
        }

    def upsert_outreach_draft(self, *, lead_id: str, draft: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO outreach_draft_state (lead_id, draft_json, updated_at, last_send_idempotency)
                VALUES (?, ?, ?, NULL)
                ON CONFLICT(lead_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    updated_at=excluded.updated_at
                """,
                (lead_id, json.dumps(draft), _utc_now()),
            )

    def get_outreach_draft(self, *, lead_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT draft_json, last_send_idempotency, updated_at FROM outreach_draft_state WHERE lead_id = ?",
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "draft": json.loads(row["draft_json"]),
            "last_send_idempotency": row["last_send_idempotency"],
            "updated_at": row["updated_at"],
        }

    def mark_outreach_sent_idempotency(self, *, lead_id: str, idempotency_key: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE outreach_draft_state
                SET last_send_idempotency = ?, updated_at = ?
                WHERE lead_id = ?
                """,
                (idempotency_key, _utc_now(), lead_id),
            )

    def get_idempotency_response(self, *, idempotency_key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT response_json FROM orchestration_idempotency WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["response_json"])

    def put_idempotency_response(self, *, idempotency_key: str, response: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO orchestration_idempotency (idempotency_key, response_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (idempotency_key, json.dumps(response), _utc_now()),
            )

    def append_evidence_edge(
        self,
        *,
        lead_id: str,
        trace_id: str,
        edge_type: str,
        claim_ref: str | None = None,
        brief_id: str | None = None,
        source_ref: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append one evidence-graph edge (specs/observability_and_logging.md §3.3)."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO evidence_graph_edges (
                    lead_id, trace_id, edge_type, claim_ref, brief_id, source_ref, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    trace_id,
                    edge_type,
                    claim_ref,
                    brief_id,
                    source_ref,
                    json.dumps(payload or {}),
                    _utc_now(),
                ),
            )

    def list_evidence_edges(self, *, lead_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, lead_id, trace_id, edge_type, claim_ref, brief_id, source_ref, payload_json, created_at
                FROM evidence_graph_edges
                WHERE lead_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (lead_id, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "lead_id": row["lead_id"],
                "trace_id": row["trace_id"],
                "edge_type": row["edge_type"],
                "claim_ref": row["claim_ref"],
                "brief_id": row["brief_id"],
                "source_ref": row["source_ref"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete_pipeline_run(self, *, lead_id: str) -> bool:
        """Delete a lead pipeline and related state rows for operator cleanup in UI."""
        with self._conn() as conn:
            exists = conn.execute("SELECT 1 FROM pipeline_runs WHERE lead_id = ? LIMIT 1", (lead_id,)).fetchone()
            if exists is None:
                return False
            for table in (
                "lead_session_state",
                "conversation_state",
                "message_log",
                "sms_consent_state",
                "phone_lead_map",
                "lead_briefs",
                "lead_enrichment_cache",
                "act2_enrichment_briefs",
                "email_threads",
                "outreach_draft_state",
                "evidence_graph_edges",
                "pipeline_runs",
            ):
                conn.execute(f"DELETE FROM {table} WHERE lead_id = ?", (lead_id,))
            return True
