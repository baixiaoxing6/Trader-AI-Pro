# Signal-mode operations

## 1. Prepare environment

```bash
cp .env.example .env
```

Signal mode does not require Bybit credentials. Configure Telegram in `.env` only when notifications are required.

## 2. Validate tracked configuration

```bash
make validate
```

Validation checks Python syntax, JSON syntax, Docker Compose syntax, and the dry-run safety invariants.

## 3. Download historical data

```bash
make pull
make download-data
```

The command downloads the configured Bybit perpetual pairs for the base and informative timeframes. FreqAI also updates required live data when the service starts.

## 4. Run a historical test

```bash
make backtest TIMERANGE=20260101-20260701
```

Do not assess the strategy using only aggregate profit. At minimum review trade count, long/short balance, maximum drawdown, fee/funding impact, prediction coverage, rejected predictions, and stability across multiple non-overlapping periods.

## 5. Start signal mode

```bash
make up
make logs
```

Expected startup evidence:

- exchange is Bybit;
- trading mode is futures with isolated margin;
- dry run is enabled;
- strategy is `TraderAIProSignalStrategy`;
- model is `LightGBMRegressor`; and
- FreqAI begins training or loads the matching identifier.

## 6. Stop cleanly

```bash
make down
```

Runtime models, logs, candles, backtest results, and SQLite files remain under `user_data/` and are ignored by Git.

## Troubleshooting

### Telegram does not start

Confirm `TELEGRAM_ENABLED=true`, then check that `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are populated in `.env`. Restart the service after changing them.

### No predictions are accepted

Inspect `do_predict` in backtest exports and logs. Do not simply remove the quality gate. First verify data coverage, informative timeframes, model identifier, feature NaNs, and DI threshold behavior.

### Bybit pair errors

USDT perpetual symbols must use the settlement suffix, for example `BTC/USDT:USDT`. Signal mode supports isolated futures only.

### A live order appears possible

Stop the service immediately with `make down` and run `make validate`. The checked-in signal service must not receive exchange credentials and must keep `FREQTRADE__DRY_RUN=true`.
