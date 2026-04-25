"""Inspect runtime email logs without shell-quoting headaches."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any
import sys

# Allow running directly via `python agent/scripts/check_email_logs.py ...`
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.config.settings import get_settings


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _print_rows(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("No rows found.")
        return
    for row in rows:
        payload: dict[str, Any] = dict(row)
        meta = payload.get("metadata")
        if isinstance(meta, str):
            try:
                payload["metadata"] = json.loads(meta)
            except Exception:
                payload["metadata"] = meta
        print(json.dumps(payload, indent=2, ensure_ascii=True))


def _query_messages(conn: sqlite3.Connection, *, lead_id: str | None, limit: int) -> list[sqlite3.Row]:
    if lead_id:
        return conn.execute(
            """
            SELECT id, lead_id, channel, direction, message_id, content, recorded_at, metadata
            FROM message_log
            WHERE lead_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (lead_id, limit),
        ).fetchall()
    return conn.execute(
        """
        SELECT id, lead_id, channel, direction, message_id, content, recorded_at, metadata
        FROM message_log
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def _query_threads(conn: sqlite3.Connection, *, lead_id: str | None, limit: int) -> list[sqlite3.Row]:
    if lead_id:
        return conn.execute(
            """
            SELECT thread_id, lead_id, last_inbound_rfc_message_id, references_header, created_at, updated_at
            FROM email_threads
            WHERE lead_id = ?
            ORDER BY datetime(updated_at) DESC
            LIMIT ?
            """,
            (lead_id, limit),
        ).fetchall()
    return conn.execute(
        """
        SELECT thread_id, lead_id, last_inbound_rfc_message_id, references_header, created_at, updated_at
        FROM email_threads
        ORDER BY datetime(updated_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def _query_sessions(conn: sqlite3.Connection, *, lead_id: str | None, limit: int) -> list[sqlite3.Row]:
    if lead_id:
        return conn.execute(
            """
            SELECT lead_id, current_stage, next_best_action, current_objective, updated_at
            FROM lead_session_state
            WHERE lead_id = ?
            ORDER BY datetime(updated_at) DESC
            LIMIT ?
            """,
            (lead_id, limit),
        ).fetchall()
    return conn.execute(
        """
        SELECT lead_id, current_stage, next_best_action, current_objective, updated_at
        FROM lead_session_state
        ORDER BY datetime(updated_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect runtime email logs and state.")
    parser.add_argument(
        "--db",
        default="",
        help="Optional sqlite DB path (defaults to STATE_DB_PATH from settings).",
    )
    parser.add_argument("--lead-id", default="", help="Optional lead ID filter.")
    parser.add_argument("--limit", type=int, default=50, help="Max rows per section.")
    parser.add_argument(
        "--section",
        choices=("messages", "threads", "sessions", "all"),
        default="all",
        help="Which section to print.",
    )
    args = parser.parse_args()

    settings = get_settings()
    db_path = args.db.strip() or settings.state_db_path
    lead_id = args.lead_id.strip() or None

    if not Path(db_path).exists():
        raise SystemExit(f"DB not found: {db_path}")

    with _connect(db_path) as conn:
        if args.section in ("messages", "all"):
            print("\n=== message_log ===")
            _print_rows(_query_messages(conn, lead_id=lead_id, limit=args.limit))
        if args.section in ("threads", "all"):
            print("\n=== email_threads ===")
            _print_rows(_query_threads(conn, lead_id=lead_id, limit=args.limit))
        if args.section in ("sessions", "all"):
            print("\n=== lead_session_state ===")
            _print_rows(_query_sessions(conn, lead_id=lead_id, limit=args.limit))


if __name__ == "__main__":
    main()
