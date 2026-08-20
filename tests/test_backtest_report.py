from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.validate_backtest import build_summary, find_latest_result, load_result


STRATEGY = "TraderAIProSignalStrategy"


def sample_result() -> dict:
    return {
        "strategy": {
            STRATEGY: {
                "trades": [{"pair": "BTC/USDT:USDT"}],
                "total_trades": 1,
                "wins": 1,
                "draws": 0,
                "losses": 0,
                "profit_total": 0.01,
                "profit_total_abs": 1.0,
                "max_drawdown_account": 0.002,
                "backtest_start": "2026-08-01 00:00:00",
                "backtest_end": "2026-08-08 00:00:00",
            }
        }
    }


class BacktestReportTests(unittest.TestCase):
    def test_build_summary_extracts_stable_metrics(self) -> None:
        summary = build_summary(sample_result(), STRATEGY, Path("result.zip"))
        self.assertEqual(summary["strategy"], STRATEGY)
        self.assertEqual(summary["total_trades"], 1)
        self.assertEqual(summary["profit_total"], 0.01)
        self.assertEqual(summary["result_file"], "result.zip")

    def test_missing_strategy_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "strategy missing"):
            build_summary({"strategy": {}}, STRATEGY, Path("result.json"))

    def test_trade_count_mismatch_is_rejected(self) -> None:
        data = sample_result()
        data["strategy"][STRATEGY]["total_trades"] = 2
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_summary(data, STRATEGY, Path("result.json"))

    def test_zip_loader_ignores_metadata_and_directory_finds_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            archive_path = directory / "backtest-result.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("backtest-result.meta.json", "{}")
                archive.writestr("backtest-result_config.json", '{"dry_run": true}')
                archive.writestr("backtest-result.json", json.dumps(sample_result()))

            self.assertEqual(find_latest_result(directory), archive_path)
            self.assertEqual(load_result(archive_path), sample_result())


if __name__ == "__main__":
    unittest.main()
