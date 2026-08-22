# Trader AI Pro

Trader AI Pro is a Freqtrade + FreqAI project for Bybit USDT perpetual markets. The first milestone is **signal mode**: FreqAI trains and predicts continuously, Freqtrade records paper positions, and Telegram emits entry/exit notifications without sending real orders to Bybit.

## Safety contract

- `dry_run` is enabled in the Freqtrade config.
- Docker forces `FREQTRADE__DRY_RUN=true` at runtime.
- No exchange API key or secret is accepted by the signal-mode Compose service.
- Bybit uses USDT-settled perpetual pairs with isolated margin and 1x strategy leverage.
- Telegram credentials live only in the untracked `.env` file.

Signal mode is deliberately separate from any future execution mode. Do not reuse this configuration as a live-trading configuration.

## Included in the first milestone

- Bybit USDT perpetual configuration for `BTC/USDT:USDT`, `ETH/USDT:USDT`, and `SOL/USDT:USDT`.
- FreqAI regression baseline using the built-in `LightGBMRegressor`.
- Long and short signals gated by prediction quality, trend, momentum, and volume.
- Telegram entry/exit notifications generated from paper trades.
- Docker Compose operations, data download, backtesting, static safety validation, and CI.
- A reproducible end-to-end Bybit/FreqAI smoke backtest with retained result evidence.

## Quick start

Requirements: Docker Engine with Docker Compose v2, GNU Make, and Python 3.11+ for local validation.

```bash
cp .env.example .env
make validate
make pull
make download-data
make up
make logs
```

Telegram is optional. To enable it, edit only `.env`:

```dotenv
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=replace-with-bot-token
TELEGRAM_CHAT_ID=replace-with-chat-id
```

Then restart the service:

```bash
make down
make up
```

## Windows one-file launcher

Windows users can download the `Trader-AI-Pro-Windows` artifact from the latest
[`Windows Launcher`](../../actions/workflows/windows-launcher.yml) workflow run. Extract the
artifact and open `Trader-AI-Pro.exe`. Python, Git, and GNU Make are not required for this path.

Docker Desktop is still required because the launcher runs the official Freqtrade/FreqAI image.
The first screen stores Telegram settings only in `%LOCALAPPDATA%\TraderAIPro\.env`. Click
**一键安装并启动** to pull the image, download 90 days of Bybit candles, and start signal mode.
The same application can stop the service, show status and logs, open the runtime directory, and
run the complete offline smoke backtest.

The executable remains a signal-only launcher: it validates `dry_run=true`, never accepts Bybit
API credentials, and does not send real orders.

## Backtesting

Download data first, then pass an explicit timerange:

```bash
make download-data
make backtest TIMERANGE=20260101-20260701
```

FreqAI backtests train historical models and may take significantly longer than ordinary strategy backtests.

To run the same compact integration test used by CI:

```bash
make smoke-backtest
```

It downloads a fixed window from Bybit's official public futures trade archive, builds Freqtrade candles, trains a small FreqAI model, runs an uncached backtest, and writes `user_data/backtest_results/ci-summary.json`. The fixed window makes pipeline failures comparable.

## Project structure

```text
.
├── .github/workflows/
│   ├── backtest-smoke.yml
│   └── ci.yml
├── docker-compose.yml
├── docs/
│   ├── acceptance.md
│   ├── architecture.md
│   └── operations.md
├── scripts/
│   ├── validate.py
│   ├── validate_backtest.py
│   ├── prepare_bybit_public_data.py
│   └── run_offline_backtest.py
├── tests/
│   ├── test_backtest_report.py
│   └── test_signal_mode.py
└── user_data/
    ├── configs/
    │   ├── config.backtest-smoke.json
    │   └── config.signal.json
    └── strategies/TraderAIProSignalStrategy.py
```

## Development workflow

- `main`: stable checkpoints.
- `develop`: active integration branch.
- Future work should use short-lived `feat/*` or `fix/*` branches from `develop`.

Read [acceptance.md](docs/acceptance.md) for the delivery criteria, [architecture.md](docs/architecture.md) for component boundaries, and [operations.md](docs/operations.md) for operating procedures.

## Important

This repository provides engineering infrastructure and a research baseline, not investment advice or a claim of profitability. A model must pass leakage checks, walk-forward backtests, fee/funding/slippage analysis, and an extended dry-run observation period before live execution is considered.
