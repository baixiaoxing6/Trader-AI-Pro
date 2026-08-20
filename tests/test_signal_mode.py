from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "user_data/configs/config.signal.json"
SMOKE_CONFIG_PATH = ROOT / "user_data/configs/config.backtest-smoke.json"
STRATEGY_PATH = ROOT / "user_data/strategies/TraderAIProSignalStrategy.py"
COMPOSE_PATH = ROOT / "docker-compose.yml"
SMOKE_WORKFLOW_PATH = ROOT / ".github/workflows/backtest-smoke.yml"


class SignalConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_dry_run_is_enabled(self) -> None:
        self.assertIs(self.config["dry_run"], True)
        self.assertFalse(self.config["force_entry_enable"])

    def test_bybit_usdt_perpetual_is_isolated(self) -> None:
        self.assertEqual(self.config["exchange"]["name"], "bybit")
        self.assertEqual(self.config["trading_mode"], "futures")
        self.assertEqual(self.config["margin_mode"], "isolated")
        for pair in self.config["exchange"]["pair_whitelist"]:
            self.assertTrue(pair.endswith("/USDT:USDT"), pair)

    def test_no_credentials_are_committed(self) -> None:
        self.assertEqual(self.config["exchange"]["api_key"], "")
        self.assertEqual(self.config["exchange"]["secret"], "")
        self.assertEqual(self.config["telegram"]["token"], "")
        self.assertEqual(self.config["telegram"]["chat_id"], "")

    def test_freqai_is_enabled_with_static_pairs(self) -> None:
        self.assertTrue(self.config["freqai"]["enabled"])
        self.assertEqual(self.config["pairlists"], [{"method": "StaticPairList"}])


class StrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = STRATEGY_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(STRATEGY_PATH))

    def test_strategy_syntax_and_class(self) -> None:
        names = {node.name for node in self.tree.body if isinstance(node, ast.ClassDef)}
        self.assertIn("TraderAIProSignalStrategy", names)

    def test_freqai_and_both_directions_are_present(self) -> None:
        self.assertIn("self.freqai.start", self.source)
        self.assertIn("enter_long", self.source)
        self.assertIn("enter_short", self.source)
        self.assertIn("exit_long", self.source)
        self.assertIn("exit_short", self.source)

    def test_leverage_is_capped_at_one(self) -> None:
        self.assertIn("return min(1.0, max_leverage)", self.source)


class ComposeTests(unittest.TestCase):
    def test_runtime_forces_dry_run_and_does_not_forward_exchange_keys(self) -> None:
        compose = COMPOSE_PATH.read_text(encoding="utf-8")
        self.assertIn('FREQTRADE__DRY_RUN: "true"', compose)
        self.assertNotIn("FREQTRADE__EXCHANGE__KEY", compose)
        self.assertNotIn("FREQTRADE__EXCHANGE__SECRET", compose)


class SmokeBacktestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(SMOKE_CONFIG_PATH.read_text(encoding="utf-8"))
        cls.workflow = SMOKE_WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_smoke_config_is_small_and_credential_free(self) -> None:
        self.assertEqual(self.config["exchange"]["pair_whitelist"], ["BTC/USDT:USDT"])
        self.assertNotIn("api_key", self.config["exchange"])
        self.assertNotIn("secret", self.config["exchange"])
        self.assertFalse(self.config["freqai"]["save_backtest_models"])
        self.assertEqual(self.config["freqai"]["feature_parameters"]["include_corr_pairlist"], [])

    def test_smoke_workflow_is_uncached_and_uses_no_secrets(self) -> None:
        self.assertIn("--cache none", self.workflow)
        self.assertIn("validate_backtest.py", self.workflow)
        self.assertNotIn("secrets.", self.workflow)


if __name__ == "__main__":
    unittest.main()
