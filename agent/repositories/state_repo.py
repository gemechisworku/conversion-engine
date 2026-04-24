"""SQLite-backed runtime state repository."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


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
