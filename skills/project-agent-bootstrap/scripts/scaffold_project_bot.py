#!/usr/bin/env python3
"""Create a non-secret, fail-closed project bot starter from the bundled asset."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "project-bot-starter"
TEXT_SUFFIXES = {
    "",
    ".example",
    ".json",
    ".md",
    ".py",
    ".service",
    ".template",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("name must contain at least one ASCII letter or digit")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", slug):
        raise ValueError("derived slug must start with a letter and contain 2-63 characters")
    return slug


def parse_databases(value: str) -> list[str]:
    allowed = {"none", "oracle", "postgresql", "mysql"}
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not items:
        items = ["none"]
    invalid = sorted(set(items) - allowed)
    if invalid:
        raise ValueError(f"unsupported databases: {', '.join(invalid)}")
    if "none" in items and len(items) > 1:
        raise ValueError("database 'none' cannot be combined with another engine")
    return list(dict.fromkeys(items))


def parse_database_sources(values: list[str]) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in values:
        if ":" not in raw:
            raise ValueError("database environment must use ENVIRONMENT:ENGINE")
        environment, engine = (part.strip() for part in raw.split(":", 1))
        environment = environment.upper()
        engine = engine.lower()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,31}", environment):
            raise ValueError(f"invalid database environment label: {environment!r}")
        if engine not in {"oracle", "postgresql", "mysql"}:
            raise ValueError(f"unsupported database engine: {engine}")
        if environment in seen:
            raise ValueError(f"duplicate database environment: {environment}")
        seen.add(environment)
        sources.append(
            {
                "environment": environment,
                "engine": engine,
                "dsn_env": f"DB_{environment}_DSN",
                "user_env": f"DB_{environment}_USER",
                "password_env": f"DB_{environment}_PASSWORD",
                "read_only_principal_required": True,
                "enabled": False,
            }
        )
    return sources


def prepare_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"output exists and is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"refusing to overwrite non-empty directory: {path}")
    else:
        path.mkdir(parents=True)


def render_tree(
    source: Path,
    target: Path,
    replacements: dict[str, str],
    *,
    service: str,
) -> None:
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if relative.parts[:1] == ("service",) and item.is_file():
            if service == "none":
                continue
            if service == "launchd" and "launchd" not in item.name:
                continue
            if service == "systemd" and "systemd" not in item.name:
                continue
        rendered_parts = [replacements.get(part, part) for part in relative.parts]
        destination = target.joinpath(*rendered_parts)
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if item.suffix.lower() in TEXT_SUFFIXES or item.name.startswith("."):
            text = item.read_text(encoding="utf-8")
            for key, value in replacements.items():
                text = text.replace(key, value)
            destination.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(item, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Human-facing project bot name")
    parser.add_argument(
        "--slug",
        default="",
        help="ASCII package slug; required when --name has no ASCII letters",
    )
    parser.add_argument("--output", required=True, help="New or empty output directory")
    parser.add_argument("--bot-name", default="", help="Feishu bot display name placeholder")
    parser.add_argument(
        "--service",
        choices=("launchd", "systemd", "none"),
        default="none",
    )
    parser.add_argument(
        "--databases",
        default="none",
        help="Comma-separated: oracle,postgresql,mysql,none",
    )
    parser.add_argument(
        "--database-env",
        action="append",
        default=[],
        metavar="ENVIRONMENT:ENGINE",
        help="Repeat for concrete sources, for example UAT:oracle",
    )
    parser.add_argument(
        "--install-root",
        default="/ABSOLUTE/PROJECT/PATH",
        help="Absolute deployment path used only in the preflight service template",
    )
    args = parser.parse_args()

    if not TEMPLATE_ROOT.is_dir():
        raise SystemExit(f"template directory is missing: {TEMPLATE_ROOT}")

    try:
        slug = slugify(args.slug or args.name)
        package = slug.replace("-", "_")
        output = Path(args.output).expanduser().resolve()
        databases = parse_databases(args.databases)
        database_sources = parse_database_sources(args.database_env)
        if database_sources:
            source_engines = list(dict.fromkeys(str(item["engine"]) for item in database_sources))
            if databases == ["none"]:
                databases = source_engines
            elif not set(source_engines).issubset(databases):
                raise ValueError("--database-env uses an engine missing from --databases")
        install_root = args.install_root.strip()
        if install_root != "/ABSOLUTE/PROJECT/PATH" and not Path(install_root).is_absolute():
            raise ValueError("--install-root must be an absolute path")
        prepare_output(output)
    except ValueError as exc:
        parser.error(str(exc))

    replacements = {
        "__BOT_SLUG__": slug,
        "__PACKAGE_NAME__": package,
        "__BOT_TITLE__": args.name.strip(),
        "__FEISHU_BOT_NAME__": (args.bot_name or args.name).strip(),
        "__SERVICE_KIND__": args.service,
        "__DATABASE_ENGINES_JSON__": json.dumps(databases, ensure_ascii=False),
        "__DATABASE_SOURCES_JSON__": json.dumps(database_sources, ensure_ascii=False),
        "__DATABASE_ENV_LINES__": (
            "\n".join(
                line
                for source in database_sources
                for line in (
                    f"{source['dsn_env']}=",
                    f"{source['user_env']}=",
                    f"{source['password_env']}=",
                )
            )
            or "# No database environments selected."
        ),
        "__INSTALL_ROOT__": install_root,
    }
    render_tree(TEMPLATE_ROOT, output, replacements, service=args.service)

    manifest = {
        "schema_version": 1,
        "generator": "project-agent-bootstrap",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": args.name.strip(),
        "slug": slug,
        "package": package,
        "service": args.service,
        "databases": databases,
        "database_sources": database_sources,
        "secrets_embedded": False,
        "scaffold_only": True,
    }
    (output / ".project-agent-bootstrap.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "created",
                "output": str(output),
                "package": package,
                "next": [
                    "Review config/bot.example.json and .env.example",
                    "Set secrets locally without committing them",
                    "Create an isolated virtual environment and run python -m pip install -e .",
                    "Run python -m unittest discover -s tests -v from that environment",
                    "Run the skill's validate_scaffold.py",
                    "Implement and live-test adapters before marking deployment ready",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
