"""Offline preflight checks that never print secret values."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import BotConfig


def command_available(command: str) -> bool:
    candidate = Path(command).expanduser()
    if candidate.is_absolute() or "/" in command:
        return candidate.is_file()
    return shutil.which(command) is not None


def run_preflight(config: BotConfig, *, live: bool) -> dict[str, object]:
    config.validate(live=live)
    checks = {
        "project_root_exists": config.project_root.is_dir(),
        "state_parent_resolvable": config.state_path.parent.exists()
        or config.state_path.parent.parent.exists(),
        "codex_command_available": command_available(config.codex_command),
        "chat_allowlist_ready": bool(config.allowed_chat_ids),
        "dry_run": config.dry_run,
        "real_writes_disabled": not config.allow_real_writes,
        "scaffold_completed": not config.scaffold_only,
        "feishu_identity_verified": config.feishu_identity_verified,
        "event_subscription_verified": config.event_subscription_verified,
        "codex_adapter_ready": config.codex_adapter_ready,
        "required_connectors_ready": config.required_connectors_ready,
    }
    required = ["project_root_exists", "codex_command_available", "real_writes_disabled"]
    if live:
        required.extend(
            [
                "chat_allowlist_ready",
                "scaffold_completed",
                "feishu_identity_verified",
                "event_subscription_verified",
                "codex_adapter_ready",
                "required_connectors_ready",
            ]
        )
    return {
        "mode": "live-prerequisites" if live else "offline",
        "ok": all(bool(checks[name]) for name in required),
        "checks": checks,
        "config": config.public_summary(),
        "secrets_printed": False,
    }
