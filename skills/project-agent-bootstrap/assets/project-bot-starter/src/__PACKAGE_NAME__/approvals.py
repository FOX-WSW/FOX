"""Exact, expiring, one-time approval records for future bounded capabilities."""

from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


class ApprovalDenied(ValueError):
    """Raised when an approval is missing, expired, mismatched, or consumed."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Approval:
    approval_id: str
    requester_id: str
    approver_id: str
    topic_id: str
    capability: str
    environment: str
    operation_hash: str
    status: str
    expires_at: str
    consumed_at: str | None


class ApprovalStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS capability_approvals (
                    approval_id TEXT PRIMARY KEY,
                    requester_id TEXT NOT NULL,
                    approver_id TEXT NOT NULL,
                    topic_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    operation_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'consumed', 'expired')),
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT
                )
                """
            )

    @staticmethod
    def _validate_hash(operation_hash: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", operation_hash):
            raise ValueError("operation_hash must be a lowercase SHA-256 hex digest")

    def request(
        self,
        *,
        requester_id: str,
        approver_id: str,
        topic_id: str,
        capability: str,
        environment: str,
        operation_hash: str,
        ttl_seconds: int = 900,
        require_distinct_approver: bool = True,
    ) -> str:
        values = (requester_id, approver_id, topic_id, capability, environment)
        if any(not value.strip() for value in values):
            raise ValueError("approval identity, topic, capability, and environment are required")
        if require_distinct_approver and requester_id == approver_id:
            raise ValueError("requester and approver must be different")
        if ttl_seconds <= 0 or ttl_seconds > 86400:
            raise ValueError("ttl_seconds must be between 1 and 86400")
        self._validate_hash(operation_hash)
        approval_id = uuid.uuid4().hex
        now = utc_now()
        expires = now + timedelta(seconds=ttl_seconds)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO capability_approvals(
                    approval_id, requester_id, approver_id, topic_id, capability,
                    environment, operation_hash, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    approval_id,
                    requester_id,
                    approver_id,
                    topic_id,
                    capability,
                    environment,
                    operation_hash,
                    now.isoformat(timespec="seconds"),
                    expires.isoformat(timespec="seconds"),
                ),
            )
        return approval_id

    def approve(self, approval_id: str, *, actor_id: str) -> None:
        now = utc_now()
        expired = False
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM capability_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if row is None:
                raise ApprovalDenied("approval not found")
            if str(row["approver_id"]) != actor_id:
                raise ApprovalDenied("actor is not the bound approver")
            if str(row["status"]) != "pending":
                raise ApprovalDenied("approval is not pending")
            if str(row["expires_at"]) <= now.isoformat(timespec="seconds"):
                connection.execute(
                    "UPDATE capability_approvals SET status = 'expired' WHERE approval_id = ?",
                    (approval_id,),
                )
                expired = True
            else:
                connection.execute(
                    """
                    UPDATE capability_approvals
                       SET status = 'approved', approved_at = ?
                     WHERE approval_id = ? AND status = 'pending'
                    """,
                    (now.isoformat(timespec="seconds"), approval_id),
                )
        if expired:
            raise ApprovalDenied("approval expired")

    def consume(
        self,
        approval_id: str,
        *,
        requester_id: str,
        topic_id: str,
        capability: str,
        environment: str,
        operation_hash: str,
    ) -> Approval:
        self._validate_hash(operation_hash)
        expected = {
            "requester_id": requester_id,
            "topic_id": topic_id,
            "capability": capability,
            "environment": environment,
            "operation_hash": operation_hash,
        }
        now_text = utc_now().isoformat(timespec="seconds")
        expired = False
        updated = None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM capability_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if row is None:
                raise ApprovalDenied("approval not found")
            if str(row["status"]) != "approved":
                raise ApprovalDenied("approval is not approved or was already consumed")
            if str(row["expires_at"]) <= now_text:
                connection.execute(
                    "UPDATE capability_approvals SET status = 'expired' WHERE approval_id = ?",
                    (approval_id,),
                )
                expired = True
            else:
                for field, value in expected.items():
                    if str(row[field]) != value:
                        raise ApprovalDenied(f"approval binding mismatch: {field}")
                cursor = connection.execute(
                    """
                    UPDATE capability_approvals
                       SET status = 'consumed', consumed_at = ?
                     WHERE approval_id = ? AND status = 'approved'
                    """,
                    (now_text, approval_id),
                )
                if cursor.rowcount != 1:
                    raise ApprovalDenied("approval was consumed concurrently")
                updated = connection.execute(
                    "SELECT * FROM capability_approvals WHERE approval_id = ?",
                    (approval_id,),
                ).fetchone()
        if expired:
            raise ApprovalDenied("approval expired")
        if updated is None:
            raise ApprovalDenied("approval result missing")
        fields = {field: updated[field] for field in Approval.__dataclass_fields__}
        return Approval(**fields)

    def status(self, approval_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM capability_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        return str(row["status"]) if row else None
