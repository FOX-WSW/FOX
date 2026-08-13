from __future__ import annotations

import tempfile
import unittest

from __PACKAGE_NAME__.config import BotConfig
from __PACKAGE_NAME__.preflight import run_preflight


class PreflightTests(unittest.TestCase):
    def test_generated_scaffold_never_reports_live_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = BotConfig.from_env(
                {
                    "PROJECT_BOT_ROOT": directory,
                    "BOT_ALLOWED_CHAT_IDS": "chat-a",
                    "BOT_CODEX_COMMAND": "/usr/bin/true",
                },
                live=True,
            )
            report = run_preflight(config, live=True)
            self.assertFalse(report["ok"])
            self.assertFalse(report["checks"]["scaffold_completed"])
            self.assertFalse(report["checks"]["feishu_identity_verified"])

    def test_integrator_attestations_are_required_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = {
                "PROJECT_BOT_ROOT": directory,
                "BOT_ALLOWED_CHAT_IDS": "chat-a",
                "BOT_CODEX_COMMAND": "/usr/bin/true",
                "BOT_SCAFFOLD_ONLY": "false",
                "BOT_FEISHU_IDENTITY_VERIFIED": "true",
                "BOT_EVENT_SUBSCRIPTION_VERIFIED": "true",
                "BOT_CODEX_ADAPTER_READY": "true",
                "BOT_REQUIRED_CONNECTORS_READY": "true",
            }
            report = run_preflight(BotConfig.from_env(values, live=True), live=True)
            self.assertTrue(report["ok"])
            self.assertNotIn("FEISHU_APP_SECRET", str(report))


if __name__ == "__main__":
    unittest.main()
