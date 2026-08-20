#!/usr/bin/env python3
"""Validate a Freqtrade backtest export and emit a compact CI summary."""

from __future__ import annotations

import argparse
import json
import math
import sys
import zipfile
from pathlib import Path
from typing import Any


IGNORED_JSON_NAMES = {".last_result.json", "ci-summary.json"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def find_latest_result(path: Path) -> Path:
    """Return the newest Freqtrade result archive or JSON export."""
    if path.is_file():
        return path

    require(path.is_dir(), f"backtest result path does not exist: {path}")
    candidates = [
        candidate
        for candidate in path.iterdir()
        if candidate.is_file()
        and (
            candidate.suffix == ".zip"
            or (
                candidate.suffix == ".json"
                and candidate.name not in IGNORED_JSON_NAMES
                and not candidate.name.endswith(".meta.json")
                and not candidate.name.endswith("_config.json")
            )
        )
    ]
    require(bool(candidates), f"no Freqtrade backtest export found in {path}")
    return max(candidates, key=lambda candidate: candidate.stat().st_mtime_ns)


def load_result(path: Path) -> dict[str, Any]:
    """Load the result JSON from a plain export or Freqtrade zip archive."""
    if path.suffix != ".zip":
        data = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(data, dict), "backtest result root must be an object")
        return data

    with zipfile.ZipFile(path) as archive:
        json_names = [
            name
            for name in archive.namelist()
            if name.endswith(".json")
            and not name.endswith(".meta.json")
            and Path(name).name not in IGNORED_JSON_NAMES
        ]
        results: list[dict[str, Any]] = []
        for name in json_names:
            with archive.open(name) as handle:
                candidate = json.load(handle)
            if isinstance(candidate, dict) and isinstance(candidate.get("strategy"), dict):
                results.append(candidate)

        require(bool(results), f"no result JSON found in archive: {path}")
        require(len(results) == 1, f"ambiguous result JSON files in archive: {path}")
        data = results[0]

    require(isinstance(data, dict), "backtest result root must be an object")
    return data


def finite_number(value: Any, field: str) -> int | float:
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{field} must be numeric",
    )
    require(math.isfinite(value), f"{field} must be finite")
    return value


def build_summary(
    data: dict[str, Any],
    strategy_name: str,
    result_file: Path,
) -> dict[str, Any]:
    """Validate the requested strategy payload and select stable metrics."""
    strategies = data.get("strategy")
    require(isinstance(strategies, dict), "backtest result has no strategy object")
    require(strategy_name in strategies, f"strategy missing from result: {strategy_name}")

    result = strategies[strategy_name]
    require(isinstance(result, dict), "strategy result must be an object")
    trades = result.get("trades")
    require(isinstance(trades, list), "strategy result must contain a trades list")

    total_trades = finite_number(result.get("total_trades", len(trades)), "total_trades")
    require(isinstance(total_trades, int), "total_trades must be an integer")
    require(total_trades >= 0, "total_trades must not be negative")
    require(total_trades == len(trades), "total_trades does not match the trades list")

    summary: dict[str, Any] = {
        "strategy": strategy_name,
        "result_file": result_file.name,
        "total_trades": total_trades,
    }
    numeric_fields = (
        "wins",
        "draws",
        "losses",
        "profit_total",
        "profit_total_abs",
        "max_drawdown_account",
    )
    for field in numeric_fields:
        if field in result:
            summary[field] = finite_number(result[field], field)

    for field in ("backtest_start", "backtest_end"):
        if field in result:
            require(isinstance(result[field], str), f"{field} must be a string")
            summary[field] = result[field]

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "result",
        type=Path,
        help="Freqtrade result zip/JSON or a directory containing exports",
    )
    parser.add_argument(
        "--strategy",
        default="TraderAIProSignalStrategy",
        help="strategy key expected in the backtest export",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="summary JSON destination (default: <result-dir>/ci-summary.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result_file = find_latest_result(args.result)
        data = load_result(result_file)
        summary = build_summary(data, args.strategy, result_file)
        output = args.output or result_file.parent / "ci-summary.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"BACKTEST VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Backtest report validated; CI summary written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
