from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from __PACKAGE_NAME__.config import BotConfig, ConfigError


class ConfigTests(unittest.TestCase):
    def test_live_mode_requires_chat_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {"PROJECT_BOT_ROOT": directory}
            with self.assertRaisesRegex(ConfigError, "BOT_ALLOWED_CHAT_IDS"):
                BotConfig.from_env(env, live=True)

    def test_safe_live_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = BotConfig.from_env(
                {
                    "PROJECT_BOT_ROOT": directory,
                    "BOT_ALLOWED_CHAT_IDS": "chat-a, chat-b",
                    "BOT_APPROVED_STATE_ROOT": "state",
                    "BOT_STATE_PATH": "state/bot.sqlite3",
                },
                live=True,
            )
            self.assertEqual(config.allowed_chat_ids, frozenset({"chat-a", "chat-b"}))
            self.assertEqual(
                config.state_path,
                (Path(directory) / "state/bot.sqlite3").resolve(),
            )
            self.assertTrue(config.dry_run)
            self.assertFalse(config.allow_real_writes)

    def test_live_mode_requires_explicit_project_root(self) -> None:
        with self.assertRaisesRegex(ConfigError, "PROJECT_BOT_ROOT"):
            BotConfig.from_env({"BOT_ALLOWED_CHAT_IDS": "chat-a"}, live=True)

    def test_state_path_must_stay_in_approved_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "PROJECT_BOT_ROOT": directory,
                "BOT_APPROVED_STATE_ROOT": "state",
                "BOT_STATE_PATH": str(Path(directory).parent / "outside.sqlite3"),
            }
            with self.assertRaisesRegex(ConfigError, "BOT_APPROVED_STATE_ROOT"):
                BotConfig.from_env(env)

    def test_generic_real_write_switch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "PROJECT_BOT_ROOT": directory,
                "BOT_ALLOWED_CHAT_IDS": "chat-a",
                "BOT_DRY_RUN": "false",
                "BOT_ALLOW_REAL_WRITES": "true",
            }
            with self.assertRaisesRegex(ConfigError, "generic write mode"):
                BotConfig.from_env(env, live=True)


if __name__ == "__main__":
    unittest.main()
