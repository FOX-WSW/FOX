"""Typed, fail-closed configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


class ConfigError(ValueError):
    """Raised when configuration would weaken a required safety boundary."""


def parse_bool(name: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ConfigError(f"{name} must be one of true/false, 1/0, yes/no, on/off")


def parse_positive_int(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive")
    return value


def parse_chat_ids(raw: str) -> frozenset[str]:
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class BotConfig:
    project_root: Path
    approved_state_root: Path
    allowed_chat_ids: frozenset[str]
    dry_run: bool
    allow_real_writes: bool
    scaffold_only: bool
    feishu_identity_verified: bool
    event_subscription_verified: bool
    codex_adapter_ready: bool
    required_connectors_ready: bool
    state_path: Path
    codex_command: str
    max_topic_concurrency: int
    query_timeout_seconds: int
    query_row_limit: int

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        live: bool = False,
    ) -> "BotConfig":
        values = os.environ if env is None else env
        root_raw = values.get("PROJECT_BOT_ROOT", "").strip()
        if live and not root_raw:
            raise ConfigError("PROJECT_BOT_ROOT must be explicitly configured in live mode")
        root = Path(root_raw).expanduser().resolve() if root_raw else Path.cwd().resolve()
        state_root_raw = values.get("BOT_APPROVED_STATE_ROOT", "./data").strip()
        state_root = Path(state_root_raw).expanduser()
        if not state_root.is_absolute():
            state_root = root / state_root
        state_root = state_root.resolve()
        state_raw = values.get("BOT_STATE_PATH", "./data/state.sqlite3").strip()
        state = Path(state_raw).expanduser()
        if not state.is_absolute():
            state = root / state
        config = cls(
            project_root=root,
            approved_state_root=state_root,
            allowed_chat_ids=parse_chat_ids(values.get("BOT_ALLOWED_CHAT_IDS", "")),
            dry_run=parse_bool("BOT_DRY_RUN", values.get("BOT_DRY_RUN", "true")),
            allow_real_writes=parse_bool(
                "BOT_ALLOW_REAL_WRITES",
                values.get("BOT_ALLOW_REAL_WRITES", "false"),
            ),
            scaffold_only=parse_bool(
                "BOT_SCAFFOLD_ONLY",
                values.get("BOT_SCAFFOLD_ONLY", "true"),
            ),
            feishu_identity_verified=parse_bool(
                "BOT_FEISHU_IDENTITY_VERIFIED",
                values.get("BOT_FEISHU_IDENTITY_VERIFIED", "false"),
            ),
            event_subscription_verified=parse_bool(
                "BOT_EVENT_SUBSCRIPTION_VERIFIED",
                values.get("BOT_EVENT_SUBSCRIPTION_VERIFIED", "false"),
            ),
            codex_adapter_ready=parse_bool(
                "BOT_CODEX_ADAPTER_READY",
                values.get("BOT_CODEX_ADAPTER_READY", "false"),
            ),
            required_connectors_ready=parse_bool(
                "BOT_REQUIRED_CONNECTORS_READY",
                values.get("BOT_REQUIRED_CONNECTORS_READY", "false"),
            ),
            state_path=state.resolve(),
            codex_command=values.get("BOT_CODEX_COMMAND", "codex").strip() or "codex",
            max_topic_concurrency=parse_positive_int(
                "BOT_MAX_TOPIC_CONCURRENCY",
                values.get("BOT_MAX_TOPIC_CONCURRENCY", "4"),
            ),
            query_timeout_seconds=parse_positive_int(
                "BOT_QUERY_TIMEOUT_SECONDS",
                values.get("BOT_QUERY_TIMEOUT_SECONDS", "30"),
            ),
            query_row_limit=parse_positive_int(
                "BOT_QUERY_ROW_LIMIT",
                values.get("BOT_QUERY_ROW_LIMIT", "500"),
            ),
        )
        config.validate(live=live)
        return config

    def validate(self, *, live: bool) -> None:
        if live and not self.allowed_chat_ids:
            raise ConfigError("BOT_ALLOWED_CHAT_IDS must be non-empty in live mode")
        if live and not self.project_root.is_dir():
            raise ConfigError(f"PROJECT_BOT_ROOT is not a directory: {self.project_root}")
        try:
            self.state_path.relative_to(self.approved_state_root)
        except ValueError as exc:
            raise ConfigError(
                "BOT_STATE_PATH must stay within BOT_APPROVED_STATE_ROOT"
            ) from exc
        if self.allow_real_writes and self.dry_run:
            raise ConfigError("real writes cannot be enabled while dry_run is true")
        if self.allow_real_writes:
            raise ConfigError(
                "generic write mode is forbidden; register and review one exact capability"
            )

    def public_summary(self) -> dict[str, object]:
        return {
            "project_root": str(self.project_root),
            "approved_state_root": str(self.approved_state_root),
            "allowed_chat_count": len(self.allowed_chat_ids),
            "dry_run": self.dry_run,
            "allow_real_writes": self.allow_real_writes,
            "scaffold_only": self.scaffold_only,
            "feishu_identity_verified": self.feishu_identity_verified,
            "event_subscription_verified": self.event_subscription_verified,
            "codex_adapter_ready": self.codex_adapter_ready,
            "required_connectors_ready": self.required_connectors_ready,
            "state_path": str(self.state_path),
            "codex_command": self.codex_command,
            "max_topic_concurrency": self.max_topic_concurrency,
            "query_timeout_seconds": self.query_timeout_seconds,
            "query_row_limit": self.query_row_limit,
        }
