#!/usr/bin/env python3
"""Validate syntax and non-negotiable signal-mode safety invariants."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "user_data/configs/config.signal.json"
SMOKE_CONFIG_PATH = ROOT / "user_data/configs/config.backtest-smoke.json"
STRATEGY_PATH = ROOT / "user_data/strategies/TraderAIProSignalStrategy.py"
COMPOSE_PATH = ROOT / "docker-compose.yml"
SMOKE_WORKFLOW_PATH = ROOT / ".github/workflows/backtest-smoke.yml"
PUBLIC_DATA_SCRIPT_PATH = ROOT / "scripts/prepare_bybit_public_data.py"
OFFLINE_BACKTEST_SCRIPT_PATH = ROOT / "scripts/run_offline_backtest.py"
WINDOWS_LAUNCHER_PATH = ROOT / "launcher/trader_ai_pro_launcher.py"
WINDOWS_WORKFLOW_PATH = ROOT / ".github/workflows/windows-launcher.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_config() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    exchange = config["exchange"]

    require(config.get("dry_run") is True, "config.signal.json must keep dry_run=true")
    require(config.get("trading_mode") == "futures", "trading_mode must be futures")
    require(config.get("margin_mode") == "isolated", "margin_mode must be isolated")
    require(exchange.get("name") == "bybit", "exchange must be bybit")
    require(exchange.get("api_key", "") == "", "signal mode must not contain an API key")
    require(exchange.get("secret", "") == "", "signal mode must not contain an exchange secret")
    require(config.get("force_entry_enable") is False, "forced entries must remain disabled")
    require(config["freqai"].get("enabled") is True, "FreqAI must be enabled")
    require(config["telegram"].get("token", "") == "", "Telegram token must not be committed")
    require(config["telegram"].get("chat_id", "") == "", "Telegram chat id must not be committed")
    require(
        not config.get("api_server", {}).get("enabled", False),
        "API server must remain disabled in signal mode",
    )

    pairs = exchange.get("pair_whitelist", [])
    require(bool(pairs), "pair_whitelist must not be empty")
    require(
        all(pair.endswith("/USDT:USDT") for pair in pairs),
        "all signal-mode pairs must be USDT-settled perpetual symbols",
    )


def validate_strategy() -> None:
    source = STRATEGY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(STRATEGY_PATH))
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    require("TraderAIProSignalStrategy" in classes, "strategy class is missing")
    require("self.freqai.start" in source, "strategy must invoke FreqAI")
    require("can_short = True" in source, "strategy must support short signals")
    require("return min(1.0, max_leverage)" in source, "strategy leverage must stay capped at 1x")


def validate_smoke_config() -> None:
    base = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    smoke = json.loads(SMOKE_CONFIG_PATH.read_text(encoding="utf-8"))
    exchange = smoke["exchange"]
    freqai = smoke["freqai"]

    require(
        exchange.get("pair_whitelist") == ["SOL/USDT:USDT"],
        "smoke backtest must use only SOL/USDT:USDT",
    )
    require("api_key" not in exchange, "smoke config must not override an exchange API key")
    require("secret" not in exchange, "smoke config must not override an exchange secret")
    require(
        freqai.get("identifier") != base["freqai"].get("identifier"),
        "smoke and signal modes must use separate model identifiers",
    )
    require(freqai.get("save_backtest_models") is False, "smoke models must not be retained")
    require(freqai.get("train_period_days") == 1, "smoke training window must remain reproducible")
    require(
        freqai["feature_parameters"].get("include_corr_pairlist") == [],
        "smoke backtest must not require additional correlation pairs",
    )


def validate_compose() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    require(
        'FREQTRADE__DRY_RUN: "true"' in compose,
        "Compose must force FREQTRADE__DRY_RUN=true",
    )
    require("FREQTRADE__EXCHANGE__KEY" not in compose, "Compose must not forward exchange keys")
    require("FREQTRADE__EXCHANGE__SECRET" not in compose, "Compose must not forward exchange secrets")


def validate_smoke_workflow() -> None:
    workflow = SMOKE_WORKFLOW_PATH.read_text(encoding="utf-8")
    require("config.signal.json" in workflow, "smoke workflow must load the base config")
    require("config.backtest-smoke.json" in workflow, "smoke workflow must load its override")
    require("validate_backtest.py" in workflow, "smoke workflow must validate its result")
    require("secrets." not in workflow, "smoke workflow must not use repository secrets")
    require("prepare_bybit_public_data.py" in workflow, "smoke workflow must prepare Bybit data")
    require("run_offline_backtest.py" in workflow, "smoke workflow must avoid region-gated APIs")


def validate_public_data_path() -> None:
    data_script = PUBLIC_DATA_SCRIPT_PATH.read_text(encoding="utf-8")
    backtest_script = OFFLINE_BACKTEST_SCRIPT_PATH.read_text(encoding="utf-8")
    require(
        'PUBLIC_ROOT = "https://public.bybit.com/trading"' in data_script,
        "smoke data must come from Bybit's public archive",
    )
    require("ExchangeResolver.load_exchange" in backtest_script, "offline runner must load Bybit")
    require("validate=False" in backtest_script, "offline runner must not contact the region-gated API")
    require('"--cache"' in backtest_script and '"none"' in backtest_script, "smoke cache must be off")


def validate_windows_launcher() -> None:
    launcher = WINDOWS_LAUNCHER_PATH.read_text(encoding="utf-8")
    workflow = WINDOWS_WORKFLOW_PATH.read_text(encoding="utf-8")
    ast.parse(launcher, filename=str(WINDOWS_LAUNCHER_PATH))
    require("validate_signal_config" in launcher, "Windows launcher must validate signal safety")
    require("FREQTRADE__DRY_RUN" in launcher, "Windows launcher must verify forced dry-run")
    require("FREQTRADE__EXCHANGE__KEY" in launcher, "Windows launcher must reject exchange keys")
    require("--onefile" in workflow, "Windows workflow must produce a one-file executable")
    require("--self-test" in workflow, "Windows workflow must test the packaged executable")
    require("actions/upload-artifact@v4" in workflow, "Windows executable must be retained")
    require("secrets." not in workflow, "Windows build must not use repository secrets")


def main() -> int:
    checks = (
        validate_config,
        validate_strategy,
        validate_smoke_config,
        validate_compose,
        validate_smoke_workflow,
        validate_public_data_path,
        validate_windows_launcher,
    )
    try:
        for check in checks:
            check()
    except (KeyError, OSError, SyntaxError, ValueError, json.JSONDecodeError) as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1

    print("Validation passed: syntax and signal-mode safety invariants are intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
