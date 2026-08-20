"""FreqAI baseline for dry-run Bybit USDT perpetual signals."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy


class TraderAIProSignalStrategy(IStrategy):
    """Research baseline that converts accepted FreqAI forecasts into paper signals."""

    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = True
    process_only_new_candles = True
    startup_candle_count: int = 200

    minimal_roi = {
        "0": 0.04,
        "120": 0.02,
        "360": 0.0,
    }
    stoploss = -0.03
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    position_adjustment_enable = False

    long_threshold = 0.004
    short_threshold = -0.004
    neutral_threshold = 0.001

    plot_config = {
        "main_plot": {
            "ema_fast": {"color": "green"},
            "ema_slow": {"color": "red"},
        },
        "subplots": {
            "Prediction": {
                "&-future_return": {"color": "blue"},
                "do_predict": {"color": "brown"},
            },
            "Momentum": {"signal_rsi": {"color": "purple"}},
        },
    }

    def feature_engineering_expand_all(
        self,
        dataframe: DataFrame,
        period: int,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        """Features expanded by period, timeframe, shift, and correlation pair."""
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-mfi-period"] = ta.MFI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        dataframe["%-ema-distance-period"] = (
            dataframe["close"] / ta.EMA(dataframe, timeperiod=period) - 1.0
        )
        dataframe["%-atr-percent-period"] = (
            ta.ATR(dataframe, timeperiod=period) / dataframe["close"]
        )

        bands = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe),
            window=period,
            stds=2.0,
        )
        dataframe["%-bb-width-period"] = (
            bands["upper"] - bands["lower"]
        ) / bands["mid"]
        dataframe["%-relative-volume-period"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )
        return dataframe

    def feature_engineering_expand_basic(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        """Features expanded by timeframe, shift, and correlation pair."""
        dataframe["%-pct-change"] = dataframe["close"].pct_change()
        dataframe["%-raw-volume"] = dataframe["volume"]
        dataframe["%-log-volume"] = np.log1p(dataframe["volume"])
        dataframe["%-raw-price"] = dataframe["close"]
        return dataframe

    def feature_engineering_standard(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        """Calendar features applied once to the base timeframe."""
        hour = dataframe["date"].dt.hour
        day = dataframe["date"].dt.dayofweek
        dataframe["%-hour-sin"] = np.sin(2 * np.pi * hour / 24)
        dataframe["%-hour-cos"] = np.cos(2 * np.pi * hour / 24)
        dataframe["%-day-sin"] = np.sin(2 * np.pi * day / 7)
        dataframe["%-day-cos"] = np.cos(2 * np.pi * day / 7)
        return dataframe

    def set_freqai_targets(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        """Predict mean forward return over the configured label horizon."""
        horizon = self.freqai_info["feature_parameters"]["label_period_candles"]
        dataframe["&-future_return"] = (
            dataframe["close"].shift(-horizon).rolling(horizon).mean()
            / dataframe["close"]
            - 1.0
        )
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Run FreqAI, then add transparent filters used by the signal rules."""
        dataframe = self.freqai.start(dataframe, metadata, self)
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["signal_rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Create long and short paper-entry signals from accepted forecasts."""
        long_condition = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-future_return"] > self.long_threshold)
            & (dataframe["ema_fast"] > dataframe["ema_slow"])
            & dataframe["signal_rsi"].between(45, 70)
            & (dataframe["volume"] > 0)
        )
        short_condition = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-future_return"] < self.short_threshold)
            & (dataframe["ema_fast"] < dataframe["ema_slow"])
            & dataframe["signal_rsi"].between(30, 55)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[long_condition, ["enter_long", "enter_tag"]] = (
            1,
            "freqai_long",
        )
        dataframe.loc[short_condition, ["enter_short", "enter_tag"]] = (
            1,
            "freqai_short",
        )
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit paper positions when the forecast or trend invalidates the signal."""
        accepted = dataframe["do_predict"] == 1
        exit_long = accepted & (
            (dataframe["&-future_return"] < -self.neutral_threshold)
            | (dataframe["ema_fast"] < dataframe["ema_slow"])
        )
        exit_short = accepted & (
            (dataframe["&-future_return"] > self.neutral_threshold)
            | (dataframe["ema_fast"] > dataframe["ema_slow"])
        )

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = (
            1,
            "forecast_reversal",
        )
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = (
            1,
            "forecast_reversal",
        )
        return dataframe

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """Keep the baseline at 1x even in dry-run futures mode."""
        return min(1.0, max_leverage)
