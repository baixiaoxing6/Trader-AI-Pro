#!/usr/bin/env python3
"""Run a Freqtrade futures backtest without contacting Bybit's region-gated API."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from freqtrade.commands.arguments import Arguments
from freqtrade.commands.optimize_commands import setup_optimize_configuration
from freqtrade.enums import RunMode
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.resolvers.exchange_resolver import ExchangeResolver


PAIR = "SOL/USDT:USDT"


def offline_market() -> dict:
    """Minimal current-style CCXT market metadata for a linear perpetual."""
    return {
        "id": "SOLUSDT",
        "symbol": PAIR,
        "base": "SOL",
        "quote": "USDT",
        "settle": "USDT",
        "baseId": "SOL",
        "quoteId": "USDT",
        "settleId": "USDT",
        "type": "swap",
        "spot": False,
        "margin": False,
        "swap": True,
        "future": False,
        "option": False,
        "contract": True,
        "linear": True,
        "inverse": False,
        "tierBased": True,
        "percentage": True,
        "taker": 0.0006,
        "maker": 0.0002,
        "contractSize": 1.0,
        "active": True,
        "expiry": None,
        "expiryDatetime": None,
        "strike": None,
        "optionType": None,
        "limits": {
            "leverage": {"min": 1.0, "max": 50.0},
            "amount": {"min": 0.1, "max": 1_000_000.0},
            "price": {"min": 0.001, "max": None},
            "cost": {"min": 5.0, "max": None},
        },
        "precision": {"price": 0.001, "amount": 0.1},
        "info": {"source": "offline-ci-fixture"},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", action="append", type=Path, required=True)
    parser.add_argument("--strategy", default="TraderAIProSignalStrategy")
    parser.add_argument("--freqaimodel", default="LightGBMRegressor")
    parser.add_argument("--timerange", default="20210705-20210707")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> dict:
    command = ["backtesting"]
    for config_path in args.config:
        command.extend(["--config", str(config_path)])
    command.extend(
        [
            "--strategy",
            args.strategy,
            "--freqaimodel",
            args.freqaimodel,
            "--timerange",
            args.timerange,
            "--export",
            "trades",
            "--cache",
            "none",
        ]
    )
    return setup_optimize_configuration(Arguments(command).get_parsed_arg(), RunMode.BACKTEST)


def main() -> int:
    args = parse_args()
    try:
        config = build_config(args)
        if config["exchange"]["pair_whitelist"] != [PAIR]:
            raise ValueError(f"offline smoke backtest requires only {PAIR}")

        exchange = ExchangeResolver.load_exchange(
            config,
            validate=False,
            load_leverage_tiers=False,
        )
        market = offline_market()
        exchange._markets = {PAIR: market}
        exchange._api.markets = {PAIR: market}
        exchange._api.markets_by_id = {market["id"]: [market]}
        exchange._leverage_tiers = {
            PAIR: [
                {
                    "minNotional": 0.0,
                    "maxNotional": 1_000_000.0,
                    "maintenanceMarginRate": 0.005,
                    "maxLeverage": 50.0,
                    "maintAmt": 0.0,
                }
            ]
        }

        backtesting = Backtesting(config, exchange=exchange)
        backtesting.start()
    except Exception as exc:
        traceback.print_exc()
        print(f"OFFLINE BACKTEST FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        Backtesting.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
