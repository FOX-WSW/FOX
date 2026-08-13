"""Deterministic policy checks; database grants remain the primary boundary."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


class PolicyDenied(ValueError):
    """Raised when a request is outside the declared capability boundary."""


WRITE_KEYWORDS = re.compile(
    r"\b(?:insert|update|delete|merge|alter|drop|truncate|create|grant|revoke|commit|rollback|call|execute|exec)\b",
    re.IGNORECASE,
)
SIDE_EFFECT_SURFACES = re.compile(
    r"\b(?:utl_http|utl_file|dbms_job|dbms_scheduler|dbms_lock|dbms_pipe|dbms_alert|dbms_java|dbms_aq|dbms_aqadm)\b",
    re.IGNORECASE,
)
LOCKING = re.compile(r"\bfor\s+update\b|\block\s+table\b", re.IGNORECASE)


def _mask_literals_and_comments(sql: str) -> str:
    result: list[str] = []
    index = 0
    state = "normal"
    while index < len(sql):
        char = sql[index]
        pair = sql[index : index + 2]
        if state == "normal" and pair == "--":
            state = "line_comment"
            result.extend("  ")
            index += 2
            continue
        if state == "normal" and pair == "/*":
            state = "block_comment"
            result.extend("  ")
            index += 2
            continue
        if state == "normal" and char == "'":
            state = "string"
            result.append(" ")
            index += 1
            continue
        if state == "line_comment":
            result.append("\n" if char == "\n" else " ")
            if char == "\n":
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if pair == "*/":
                result.extend("  ")
                index += 2
                state = "normal"
            else:
                result.append(" ")
                index += 1
            continue
        if state == "string":
            result.append(" ")
            if char == "'":
                if index + 1 < len(sql) and sql[index + 1] == "'":
                    result.append(" ")
                    index += 2
                    continue
                state = "normal"
            index += 1
            continue
        result.append(char)
        index += 1
    if state in {"string", "block_comment"}:
        raise PolicyDenied("unterminated SQL literal or comment")
    return "".join(result)


def validate_readonly_sql(sql: str) -> str:
    """Return normalized SQL when it is a single SELECT/WITH statement.

    This check cannot prove that user-defined functions are side-effect free.
    Always combine it with a least-privilege, genuinely read-only principal.
    """

    text = sql.strip()
    if not text:
        raise PolicyDenied("SQL is empty")
    masked = _mask_literals_and_comments(text).strip()
    body = masked[:-1].rstrip() if masked.endswith(";") else masked
    if ";" in body:
        raise PolicyDenied("multiple SQL statements are forbidden")
    if not re.match(r"^(?:select|with)\b", body, re.IGNORECASE):
        raise PolicyDenied("only SELECT or WITH queries are allowed")
    for rule, reason in (
        (WRITE_KEYWORDS, "write or administrative SQL is forbidden"),
        (SIDE_EFFECT_SURFACES, "side-effect package is forbidden"),
        (LOCKING, "locking SQL is forbidden"),
    ):
        if rule.search(body):
            raise PolicyDenied(reason)
    return text[:-1].rstrip() if text.endswith(";") else text


def require_allowed_chat(chat_id: str, allowed_chat_ids: frozenset[str]) -> None:
    if not allowed_chat_ids or chat_id not in allowed_chat_ids:
        raise PolicyDenied("chat is not allowlisted")


@dataclass(frozen=True)
class CapabilityRequest:
    name: str
    environment: str
    parameters: Mapping[str, Any]

    def operation_hash(self) -> str:
        payload = json.dumps(
            {
                "name": self.name,
                "environment": self.environment,
                "parameters": self.parameters,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
