#!/usr/bin/env python3
"""Validate a generated project-bot scaffold without reading external secrets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED = (
    ".env.example",
    ".gitignore",
    ".project-agent-bootstrap.json",
    "AGENTS.md",
    "README.md",
    "config/bot.example.json",
    "pyproject.toml",
    "tests/test_approvals.py",
    "tests/test_config.py",
    "tests/test_policy.py",
    "tests/test_preflight.py",
    "tests/test_runtime.py",
    "tests/test_state.py",
)
TEXT_SUFFIXES = {"", ".example", ".json", ".md", ".py", ".service", ".template", ".toml"}
SECRET_ASSIGNMENT = re.compile(
    r"(?m)^[ \t]*(?:[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|PRIVATE_KEY|COOKIE|API_KEY)[A-Z0-9_]*)[ \t]*=[ \t]*([^\s#][^\r\n]*)$"
)
STRUCTURED_SECRET = re.compile(
    r'''(?im)["'](?:password|secret|token|private[_-]?key|cookie|api[_-]?key)["']\s*:\s*["']([^"'\r\n]+)["']'''
)
YAML_SECRET = re.compile(
    r"(?im)^[ \t]*(?:password|secret|token|private[_-]?key|cookie|api[_-]?key)[ \t]*:[ \t]*([^\s#][^\r\n]*)$"
)
COMMON_TOKEN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)"
)
URL_CREDENTIAL = re.compile(r"[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@", re.IGNORECASE)
PRIVATE_ADDRESS = re.compile(
    r"(?<![0-9])(?:10(?:\.[0-9]{1,3}){3}|192\.168(?:\.[0-9]{1,3}){2}|172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2})(?![0-9])"
)


def text_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix.lower() in TEXT_SUFFIXES or path.name.startswith(".")):
            if ".git" not in path.parts:
                yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Generated project directory")
    args = parser.parse_args()
    root = Path(args.project).expanduser().resolve()
    issues: list[str] = []
    deployment_blockers: list[str] = []

    if not root.is_dir():
        issues.append(f"not a directory: {root}")
    for relative in REQUIRED:
        if not (root / relative).is_file():
            issues.append(f"missing required file: {relative}")

    manifest_path = root / ".project-agent-bootstrap.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            package = str(manifest.get("package") or "")
            if not package or not (root / "src" / package / "__init__.py").is_file():
                issues.append("manifest package does not match src package")
            if manifest.get("secrets_embedded") is not False:
                issues.append("manifest must declare secrets_embedded=false")
            if manifest.get("scaffold_only") is not True:
                issues.append("generated scaffold must keep scaffold_only=true")
            deployment_blockers.append(
                "scaffold validator cannot certify deployment readiness; complete live adapter tests"
            )
            service = str(manifest.get("service") or "none")
            service_dir = root / "service"
            service_files = list(service_dir.glob("*")) if service_dir.is_dir() else []
            if service == "none" and service_files:
                issues.append("service=none must not generate service files")
            if service in {"launchd", "systemd"} and len(service_files) != 1:
                issues.append(f"service={service} must generate exactly one preflight template")
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"invalid manifest: {exc}")

    for path in text_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root)
        if (
            "__BOT_" in text
            or "__PACKAGE_NAME__" in text
            or "__SERVICE_KIND__" in text
            or "__INSTALL_ROOT__" in text
            or "__DATABASE_" in text
        ):
            issues.append(f"unresolved template token: {relative}")
        if "/ABSOLUTE/PROJECT/PATH" in text:
            deployment_blockers.append(f"deployment path placeholder remains: {relative}")
        if PRIVATE_ADDRESS.search(text):
            issues.append(f"private network address found: {relative}")
        for match in SECRET_ASSIGNMENT.finditer(text):
            value = match.group(1).strip().strip('"\'')
            if value and value not in {"CHANGE_ME", "<set-locally>"}:
                issues.append(f"possible embedded secret: {relative}")
                break
        else:
            candidates = [
                match.group(1).strip().strip('"\'')
                for pattern in (STRUCTURED_SECRET, YAML_SECRET)
                for match in pattern.finditer(text)
            ]
            if any(value not in {"", "CHANGE_ME", "<set-locally>"} for value in candidates):
                issues.append(f"possible structured secret: {relative}")
            elif COMMON_TOKEN.search(text) or URL_CREDENTIAL.search(text):
                issues.append(f"possible credential pattern: {relative}")

    example = root / "config/bot.example.json"
    if example.is_file():
        try:
            config = json.loads(example.read_text(encoding="utf-8"))
            safety = config.get("safety") or {}
            if safety.get("dry_run") is not True:
                issues.append("config default dry_run must be true")
            if safety.get("allow_real_writes") is not False:
                issues.append("config default allow_real_writes must be false")
            if config.get("feishu", {}).get("allowed_chat_ids"):
                issues.append("example config must not contain real chat IDs")
            if config.get("lifecycle", {}).get("scaffold_only") is not True:
                issues.append("example config must declare lifecycle.scaffold_only=true")
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"invalid config/bot.example.json: {exc}")

    report = {
        "project": str(root),
        "valid": not issues,
        "deployment_ready": False,
        "validation_scope": "scaffold hygiene only",
        "secret_scan_scope": "heuristic; use a dedicated secret scanner before publishing",
        "issues": issues,
        "deployment_blockers": sorted(set(deployment_blockers)),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
