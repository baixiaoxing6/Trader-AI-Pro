# Signal-mode acceptance

The signal-mode milestone is complete when all of the following checks pass on the same commit.

| Area | Acceptance evidence |
|---|---|
| Safety | Static validation proves dry run, isolated futures, empty exchange credentials, and 1x leverage. |
| Configuration | The official `stable_freqai` image loads the checked-in config and strategy. |
| Unit tests | Signal, credential, Compose, smoke-config, and report-parser tests pass. |
| Market data | CI builds candles from Bybit's official public USDT perpetual trade archives without private credentials. |
| FreqAI | CI trains `LightGBMRegressor` using only data available before each prediction window. |
| Backtest | CI runs the strategy end to end and validates the exported result structure. |
| Evidence | The workflow retains the backtest archive and `ci-summary.json` for 14 days. |

The smoke backtest is an integration test. It is allowed to produce zero trades or a loss because its purpose is to prove that data download, feature generation, model training, inference, signal evaluation, and result export work together. Profitability requires separate walk-forward research across multiple regimes with realistic fees, funding, slippage, and untouched holdout periods.

Live orders are explicitly outside this milestone. Enabling them requires a separate configuration, risk limits, credential handling, operational alerts, and an explicit execution-readiness approval.
