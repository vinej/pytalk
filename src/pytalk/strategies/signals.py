"""Trade-signal generation for each strategy, for annotation on the Analysis chart.

Each function returns a Series (aligned to prices.index) containing "B", "S" or NaN.
Entry points are marked "B", exits (or short entries) are marked "S", mirroring what
the corresponding Strategy's next() method would trigger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pytalk.indicators import macd, rsi, sma


def _cross_signals(fast: pd.Series, slow: pd.Series, index: pd.Index) -> pd.Series:
    diff = np.sign(fast - slow).diff()
    out = pd.Series(index=index, dtype=object)
    out[diff == 2] = "B"
    out[diff == -2] = "S"
    return out


def _sma_cross(prices: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    close = prices["close"]
    return _cross_signals(sma(close, fast), sma(close, slow), prices.index)


def _macd_cross(
    prices: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.Series:
    m = macd(prices["close"], fast, slow, signal)
    return _cross_signals(m["macd"], m["signal"], prices.index)


def _rsi_reversion(
    prices: pd.DataFrame, window: int = 14, oversold: float = 30, overbought: float = 70
) -> pd.Series:
    r = rsi(prices["close"], window)
    out = pd.Series(index=prices.index, dtype=object)
    in_pos = False
    for i, val in enumerate(r.values):
        if pd.isna(val):
            continue
        if not in_pos and val < oversold:
            out.iloc[i] = "B"
            in_pos = True
        elif in_pos and val > overbought:
            out.iloc[i] = "S"
            in_pos = False
    return out


def _bollinger(prices: pd.DataFrame, window: int = 20, k: float = 2.0) -> pd.Series:
    close = prices["close"]
    mid = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = mid + k * std
    lower = mid - k * std
    out = pd.Series(index=prices.index, dtype=object)
    long_in = short_in = False
    for i in range(len(close)):
        if pd.isna(lower.iloc[i]):
            continue
        price = close.iloc[i]
        if not long_in and not short_in and price < lower.iloc[i]:
            out.iloc[i] = "B"
            long_in = True
        elif not long_in and not short_in and price > upper.iloc[i]:
            out.iloc[i] = "S"
            short_in = True
        elif long_in and price > mid.iloc[i]:
            long_in = False
        elif short_in and price < mid.iloc[i]:
            short_in = False
    return out


def _donchian(
    prices: pd.DataFrame, entry_window: int = 20, exit_window: int = 10
) -> pd.Series:
    upper = prices["high"].shift(1).rolling(entry_window).max()
    lower = prices["low"].shift(1).rolling(exit_window).min()
    close = prices["close"]
    out = pd.Series(index=prices.index, dtype=object)
    in_pos = False
    for i in range(len(close)):
        if pd.isna(upper.iloc[i]) or pd.isna(lower.iloc[i]):
            continue
        price = close.iloc[i]
        if not in_pos and price > upper.iloc[i]:
            out.iloc[i] = "B"
            in_pos = True
        elif in_pos and price < lower.iloc[i]:
            out.iloc[i] = "S"
            in_pos = False
    return out


def _vwap_reversion(prices: pd.DataFrame, window: int = 20, k: float = 1.5) -> pd.Series:
    typical = (prices["high"] + prices["low"] + prices["close"]) / 3
    volume = prices["volume"]
    vwap = (typical * volume).rolling(window).sum() / volume.rolling(window).sum()
    std = (prices["close"] - vwap).rolling(window).std()
    lower = vwap - k * std
    close = prices["close"]
    out = pd.Series(index=prices.index, dtype=object)
    in_pos = False
    for i in range(len(close)):
        if pd.isna(vwap.iloc[i]) or pd.isna(lower.iloc[i]):
            continue
        price = close.iloc[i]
        if not in_pos and price < lower.iloc[i]:
            out.iloc[i] = "B"
            in_pos = True
        elif (
            in_pos
            and i > 0
            and price > vwap.iloc[i]
            and close.iloc[i - 1] <= vwap.iloc[i - 1]
        ):
            out.iloc[i] = "S"
            in_pos = False
    return out


def _buy_hold(prices: pd.DataFrame) -> pd.Series:
    out = pd.Series(index=prices.index, dtype=object)
    if len(prices) > 0:
        out.iloc[0] = "B"
    return out


def _faber_trend(prices: pd.DataFrame, window: int = 200) -> pd.Series:
    close = prices["close"]
    sma_series = close.rolling(window).mean()
    return _cross_signals(close, sma_series, prices.index)


_SIGNALS = {
    "Buy & Hold": _buy_hold,
    "Faber Trend Filter": _faber_trend,
    "SMA Cross": _sma_cross,
    "MACD Cross": _macd_cross,
    "RSI Mean Reversion": _rsi_reversion,
    "Bollinger Mean Reversion": _bollinger,
    "Donchian Breakout": _donchian,
    "VWAP Reversion": _vwap_reversion,
}


def signals_for(strategy_name: str, prices: pd.DataFrame, **params) -> pd.Series:
    return _SIGNALS[strategy_name](prices, **params)
