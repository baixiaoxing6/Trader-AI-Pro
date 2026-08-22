from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from launcher.trader_ai_pro_launcher import (
    LauncherError,
    install_assets,
    parse_env,
    resource_root,
    validate_signal_config,
    validate_telegram,
    write_env,
)


class WindowsLauncherTests(unittest.TestCase):
    def test_packaged_assets_install_and_preserve_env(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            install_assets(resource_root(), destination)
            env_path = destination / ".env"
            env_path.write_text("TELEGRAM_ENABLED=true\nTELEGRAM_BOT_TOKEN=secret\n", encoding="utf-8")
            install_assets(resource_root(), destination)
            self.assertIn("TELEGRAM_BOT_TOKEN=secret", env_path.read_text(encoding="utf-8"))
            self.assertTrue((destination / "docker-compose.yml").is_file())
            self.assertTrue(
                (destination / "user_data/strategies/TraderAIProSignalStrategy.py").is_file()
            )

    def test_env_round_trip_and_disabled_secrets_are_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env_path = Path(temporary) / ".env"
            write_env(env_path, True, "123:abc_DEF", "-1001234567890")
            values = parse_env(env_path)
            self.assertEqual(values["TELEGRAM_ENABLED"], "true")
            self.assertEqual(values["TELEGRAM_BOT_TOKEN"], "123:abc_DEF")
            self.assertEqual(values["TELEGRAM_CHAT_ID"], "-1001234567890")
            write_env(env_path, False, "must-not-be-written", "123")
            values = parse_env(env_path)
            self.assertEqual(values["TELEGRAM_ENABLED"], "false")
            self.assertEqual(values["TELEGRAM_BOT_TOKEN"], "")
            self.assertEqual(values["TELEGRAM_CHAT_ID"], "")

    def test_invalid_enabled_telegram_values_are_rejected(self) -> None:
        with self.assertRaises(LauncherError):
            validate_telegram(True, "", "123")
        with self.assertRaises(LauncherError):
            validate_telegram(True, "123:abc", "not-a-number")

    def test_signal_config_safety_regression_is_rejected(self) -> None:
        source = resource_root() / "user_data/configs/config.signal.json"
        config = json.loads(source.read_text(encoding="utf-8"))
        config["dry_run"] = False
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unsafe.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(LauncherError):
                validate_signal_config(path)


if __name__ == "__main__":
    unittest.main()

