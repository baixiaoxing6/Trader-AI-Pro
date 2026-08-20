#!/usr/bin/env python3
"""Validate syntax and non-negotiable signal-mode safety invariants."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "user_data/configs/config.signal.json"
STRATEGY_PATH = ROOT / "user_data/strategies/TraderAIProSignalStrategy.py"
COMPOSE_PATH = ROOT / "docker-compose.yml"


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
    require(exchange.get("key", "") == "", "signal mode must not contain an exchange key")
    require(exchange.get("secret", "") == "", "signal mode must not contain an exchange secret")
    require(config.get("force_entry_enable") is False, "forced entries must remain disabled")
    require(config["freqai"].get("enabled") is True, "FreqAI must be enabled")
    require(config["telegram"].get("token", "") == "", "Telegram token must not be committed")
    require(config["telegram"].get("chat_id", "") == "", "Telegram chat id must not be committed")

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


def validate_compose() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    require(
        'FREQTRADE__DRY_RUN: "true"' in compose,
        "Compose must force FREQTRADE__DRY_RUN=true",
    )
    require("FREQTRADE__EXCHANGE__KEY" not in compose, "Compose must not forward exchange keys")
    require("FREQTRADE__EXCHANGE__SECRET" not in compose, "Compose must not forward exchange secrets")


def main() -> int:
    checks = (validate_config, validate_strategy, validate_compose)
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
