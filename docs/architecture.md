# Architecture

## Goal of milestone 1

Deliver an observable, reproducible signal pipeline before any live execution work begins. FreqAI produces forecasts, the strategy converts them into directional entry/exit signals, Freqtrade maintains paper-trade state, and Telegram reports those state changes.

```mermaid
flowchart TD
    A[Bybit public market data] --> B[Freqtrade candles]
    B --> C[FreqAI features and model]
    C --> D[Prediction quality gate]
    D --> E[Long and short rules]
    E --> F[Dry-run paper trades]
    F --> G[Telegram notifications]
```

## Component boundaries

| Component | Responsibility | Persistent output |
|---|---|---|
| Bybit adapter | Public USDT perpetual candles and market metadata | Cached candles |
| FreqAI | Feature expansion, training, inference, model lifecycle | `user_data/models/` |
| Strategy | Target definition, signal filters, exit rules, 1x leverage cap | Signal tags in dry-run database |
| Freqtrade engine | Scheduling, paper position state, notification events | SQLite database and logs |
| Telegram | Operator-facing status and paper entry/exit messages | Telegram chat history |

## Safety invariants

1. The checked-in configuration has `dry_run: true`.
2. Compose forces `FREQTRADE__DRY_RUN=true`.
3. Exchange key and secret are empty in the checked-in configuration.
4. The service does not forward exchange credentials from `.env`.
5. Bybit is configured for `futures` and `isolated` margin only.
6. Strategy leverage is capped at 1x.
7. CI fails if any of these invariants change.

The compact CI profile is a later configuration overlay. It changes only pair coverage and FreqAI training cost; the base configuration still supplies Bybit futures, isolated margin, dry run, and empty credentials.

## Signal logic

The baseline predicts the mean forward return over the configured label window. A prediction can create a paper entry only when:

- `do_predict == 1`, meaning FreqAI accepts the inference point;
- the predicted return exceeds the directional threshold;
- EMA trend agrees with the direction;
- RSI is not already at an extreme; and
- the candle has non-zero volume.

This is a research baseline, not a tuned strategy. Thresholds are constants so the first backtest results are reproducible; hyperopt and regime-specific tuning belong to later milestones.

## Branch model

- `main` stores stable checkpoints.
- `develop` integrates active work.
- Short-lived feature branches start from `develop` and return through review.

## Delivery status

1. **Complete:** signal-mode bootstrap, safety enforcement, strategy/config loading, and Telegram paper-trade notifications.
2. **Complete:** deterministic end-to-end smoke backtest and machine-readable evidence artifact.
3. **Research gate:** multi-regime walk-forward evaluation, fee/funding/slippage stress tests, and model experiments.
4. **Explicit future decision:** execution-readiness review. Live trading remains disabled until separately approved.
