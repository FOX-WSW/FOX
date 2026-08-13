"""Durable topic mapping and idempotent event state."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


TERMINAL_STATES = {"completed", "failed_visible", "withdrawn", "cancelled"}
TRANSITIONS = {
    "received": {"running", "withdrawn", "failed_visible"},
    "running": {"answer_persisted", "delivery_pending", "failed_visible", "withdrawn"},
    "answer_persisted": {"delivery_pending", "failed_visible"},
    "delivery_pending": {"delivered", "failed_visible"},
    "retry_pending": {"running", "delivery_pending", "cancelled", "failed_visible"},
    "delivered": {"completed", "failed_visible"},
    "completed": set(),
    "failed_visible": set(),
    "withdrawn": set(),
    "cancelled": set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Turn:
    event_id: str
    message_id: str
    topic_id: str
    status: str
    answer_path: str | None
    external_message_id: str | None
    attempt_count: int
    next_attempt_at: str | None
    lease_owner: str | None
    lease_token: int
    lease_expires_at: str | None


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS topic_sessions (
                    topic_id TEXT PRIMARY KEY,
                    agent_thread_id TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS message_turns (
                    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    message_id TEXT NOT NULL UNIQUE,
                    topic_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    answer_path TEXT,
                    external_message_id TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error_code TEXT,
                    lease_owner TEXT,
                    lease_token INTEGER NOT NULL DEFAULT 0,
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_turns_topic_status
                    ON message_turns(topic_id, status, created_at);
                """
            )

    def bind_topic(self, topic_id: str, agent_thread_id: str) -> None:
        if not topic_id or not agent_thread_id:
            raise ValueError("topic_id and agent_thread_id are required")
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO topic_sessions(topic_id, agent_thread_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET
                    agent_thread_id = excluded.agent_thread_id,
                    archived = 0,
                    updated_at = excluded.updated_at
                """,
                (topic_id, agent_thread_id, now),
            )

    def thread_for_topic(self, topic_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT agent_thread_id FROM topic_sessions WHERE topic_id = ? AND archived = 0",
                (topic_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def claim_event(self, event_id: str, message_id: str, topic_id: str) -> bool:
        if not event_id or not message_id or not topic_id:
            raise ValueError("event_id, message_id, and topic_id are required")
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO message_turns(
                    event_id, message_id, topic_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, 'received', ?, ?)
                """,
                (event_id, message_id, topic_id, now, now),
            )
            return cursor.rowcount == 1

    def transition(
        self,
        event_id: str,
        new_status: str,
        *,
        answer_path: str | None = None,
        external_message_id: str | None = None,
        worker_id: str | None = None,
        lease_token: int | None = None,
    ) -> None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status, lease_owner, lease_token
                  FROM message_turns
                 WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                raise KeyError(event_id)
            current = str(row[0])
            if new_status not in TRANSITIONS.get(current, set()):
                raise ValueError(f"invalid state transition: {current} -> {new_status}")
            if new_status == "answer_persisted" and not answer_path:
                raise ValueError("answer_path is required before delivery")
            if new_status == "delivered" and not external_message_id:
                raise ValueError("external_message_id is required for delivered")
            expected_owner, expected_token = self._validated_lease(
                row,
                worker_id=worker_id,
                lease_token=lease_token,
            )
            cursor = connection.execute(
                """
                UPDATE message_turns
                   SET status = ?,
                       answer_path = COALESCE(?, answer_path),
                       external_message_id = COALESCE(?, external_message_id),
                       lease_owner = CASE WHEN ? IN ('completed', 'failed_visible', 'withdrawn', 'cancelled') THEN NULL ELSE lease_owner END,
                       lease_expires_at = CASE WHEN ? IN ('completed', 'failed_visible', 'withdrawn', 'cancelled') THEN NULL ELSE lease_expires_at END,
                       updated_at = ?
                 WHERE event_id = ?
                   AND status = ?
                   AND (lease_owner = ? OR (lease_owner IS NULL AND ? IS NULL))
                   AND lease_token = ?
                """,
                (
                    new_status,
                    answer_path,
                    external_message_id,
                    new_status,
                    new_status,
                    utc_now(),
                    event_id,
                    current,
                    expected_owner,
                    expected_owner,
                    expected_token,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("concurrent state transition rejected")

    def can_start(self, event_id: str) -> bool:
        """Return true only when no earlier non-terminal turn exists in the topic."""

        terminal = tuple(sorted(TERMINAL_STATES))
        placeholders = ", ".join("?" for _ in terminal)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT topic_id, sequence_no, status, next_attempt_at
                  FROM message_turns
                 WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                raise KeyError(event_id)
            if str(row["status"]) not in {"received", "retry_pending"}:
                return False
            if row["next_attempt_at"] and str(row["next_attempt_at"]) > utc_now():
                return False
            earlier = connection.execute(
                f"""
                SELECT 1
                  FROM message_turns
                 WHERE topic_id = ?
                   AND sequence_no < ?
                   AND status NOT IN ({placeholders})
                 LIMIT 1
                """,
                (str(row["topic_id"]), int(row["sequence_no"]), *terminal),
            ).fetchone()
        return earlier is None

    @staticmethod
    def _validated_lease(
        row: sqlite3.Row,
        *,
        worker_id: str | None,
        lease_token: int | None,
    ) -> tuple[str | None, int]:
        owner = str(row["lease_owner"]) if row["lease_owner"] is not None else None
        token = int(row["lease_token"])
        if owner is None:
            if worker_id is not None or lease_token is not None:
                raise ValueError("worker lease was lost")
            return None, token
        if worker_id != owner or lease_token != token:
            raise ValueError("worker lease fencing token mismatch")
        return owner, token

    def claim_for_run(
        self,
        event_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 300,
    ) -> int | None:
        """Atomically claim a due FIFO head and move it to running."""

        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = utc_now()
        lease_expires = (
            datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        ).isoformat(timespec="seconds")
        terminal = tuple(sorted(TERMINAL_STATES))
        placeholders = ", ".join("?" for _ in terminal)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT topic_id, sequence_no, status, next_attempt_at,
                       lease_owner, lease_token, lease_expires_at
                  FROM message_turns
                 WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
            if row is None or str(row["status"]) not in {"received", "retry_pending"}:
                return None
            if row["next_attempt_at"] and str(row["next_attempt_at"]) > now:
                return None
            if row["lease_owner"] and row["lease_expires_at"] and str(row["lease_expires_at"]) > now:
                return None
            earlier = connection.execute(
                f"""
                SELECT 1
                  FROM message_turns
                 WHERE topic_id = ?
                   AND sequence_no < ?
                   AND status NOT IN ({placeholders})
                 LIMIT 1
                """,
                (str(row["topic_id"]), int(row["sequence_no"]), *terminal),
            ).fetchone()
            if earlier is not None:
                return None
            cursor = connection.execute(
                """
                UPDATE message_turns
                   SET status = 'running',
                       lease_owner = ?,
                       lease_token = lease_token + 1,
                       lease_expires_at = ?,
                       updated_at = ?
                 WHERE event_id = ? AND status = ?
                """,
                (worker_id, lease_expires, now, event_id, str(row["status"])),
            )
            if cursor.rowcount != 1:
                return None
            token_row = connection.execute(
                "SELECT lease_token FROM message_turns WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            return int(token_row["lease_token"])

    def renew_lease(
        self,
        event_id: str,
        *,
        worker_id: str,
        lease_token: int,
        lease_seconds: int = 300,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        lease_expires = (
            datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        ).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE message_turns
                   SET lease_expires_at = ?, updated_at = ?
                 WHERE event_id = ?
                   AND lease_owner = ?
                   AND lease_token = ?
                   AND status IN ('running', 'answer_persisted', 'delivery_pending')
                """,
                (lease_expires, utc_now(), event_id, worker_id, lease_token),
            )
            if cursor.rowcount != 1:
                raise ValueError("active worker lease not found")

    def recover_expired_leases(self) -> int:
        """Return crashed active turns to the durable retry queue."""

        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE message_turns
                   SET status = 'retry_pending',
                       attempt_count = attempt_count + 1,
                       next_attempt_at = ?,
                       last_error_code = 'worker_lease_expired',
                       lease_owner = NULL,
                       lease_token = lease_token + 1,
                       lease_expires_at = NULL,
                       updated_at = ?
                 WHERE status IN ('running', 'answer_persisted', 'delivery_pending')
                   AND lease_expires_at IS NOT NULL
                   AND lease_expires_at <= ?
                """,
                (now, now, now),
            )
            return cursor.rowcount

    def schedule_retry(
        self,
        event_id: str,
        *,
        error_code: str,
        delay_seconds: int,
        worker_id: str | None = None,
        lease_token: int | None = None,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        next_attempt = (
            datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        ).isoformat(timespec="seconds")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status, lease_owner, lease_token
                  FROM message_turns
                 WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                raise KeyError(event_id)
            if str(row["status"]) not in {"running", "answer_persisted", "delivery_pending"}:
                raise ValueError(f"cannot schedule retry from {row['status']}")
            expected_owner, expected_token = self._validated_lease(
                row,
                worker_id=worker_id,
                lease_token=lease_token,
            )
            cursor = connection.execute(
                """
                UPDATE message_turns
                   SET status = 'retry_pending',
                       attempt_count = attempt_count + 1,
                       next_attempt_at = ?,
                       last_error_code = ?,
                       lease_owner = NULL,
                       lease_token = lease_token + 1,
                       lease_expires_at = NULL,
                       updated_at = ?
                 WHERE event_id = ?
                   AND (lease_owner = ? OR (lease_owner IS NULL AND ? IS NULL))
                   AND lease_token = ?
                """,
                (
                    next_attempt,
                    error_code[:80],
                    utc_now(),
                    event_id,
                    expected_owner,
                    expected_owner,
                    expected_token,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("concurrent retry scheduling rejected")

    def ready_event_ids(self, *, limit: int = 100) -> list[str]:
        """Return due FIFO heads for a durable worker to claim and process."""

        if limit <= 0:
            raise ValueError("limit must be positive")
        terminal = tuple(sorted(TERMINAL_STATES))
        placeholders = ", ".join("?" for _ in terminal)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT candidate.event_id
                  FROM message_turns candidate
                 WHERE candidate.status IN ('received', 'retry_pending')
                   AND (candidate.next_attempt_at IS NULL OR candidate.next_attempt_at <= ?)
                   AND NOT EXISTS (
                       SELECT 1
                         FROM message_turns earlier
                        WHERE earlier.topic_id = candidate.topic_id
                          AND earlier.sequence_no < candidate.sequence_no
                          AND earlier.status NOT IN ({placeholders})
                   )
                 ORDER BY candidate.sequence_no
                 LIMIT ?
                """,
                (utc_now(), *terminal, limit),
            ).fetchall()
        return [str(row["event_id"]) for row in rows]

    def get_turn(self, event_id: str) -> Turn | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT event_id, message_id, topic_id, status, answer_path,
                       external_message_id, attempt_count, next_attempt_at,
                       lease_owner, lease_token, lease_expires_at
                  FROM message_turns
                 WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
        return Turn(**dict(row)) if row else None

    def get_turn_by_message(self, message_id: str) -> Turn | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT event_id, message_id, topic_id, status, answer_path,
                       external_message_id, attempt_count, next_attempt_at,
                       lease_owner, lease_token, lease_expires_at
                  FROM message_turns
                 WHERE message_id = ?
                """,
                (message_id,),
            ).fetchone()
        return Turn(**dict(row)) if row else None
