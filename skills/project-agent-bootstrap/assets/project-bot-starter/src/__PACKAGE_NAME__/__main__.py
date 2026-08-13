"""Command-line entry point for preflight and safe configuration inspection."""

from __future__ import annotations

import argparse
import json

from .config import BotConfig, ConfigError
from .preflight import run_preflight


def main() -> int:
    parser = argparse.ArgumentParser(prog="__BOT_SLUG__")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--live", action="store_true")
    subparsers.add_parser("show-config")
    args = parser.parse_args()

    try:
        config = BotConfig.from_env(live=bool(getattr(args, "live", False)))
        if args.command == "show-config":
            result: dict[str, object] = config.public_summary()
        else:
            result = run_preflight(config, live=args.live)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok", True) else 1
    except ConfigError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
