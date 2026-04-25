"""Chart indicators for each strategy, for use in the analysis UI (not backtesting)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from pytalk.indicators import macd, rsi, sma


@dataclass
class Indicator:
    name: str
    series: pd.Series
    panel: str = "price"  # "price" overlay, or "sub" for its own panel
    hlines: tuple[float, ...] = field(default_factory=tuple)


def _sma_cross(prices: pd.DataFrame, fast: int = 20, slow: int = 50) -> list[Indicator]:
    close = prices["close"]
    return [
        Indicator(f"SMA {fast}", sma(close, fast)),
        Indicator(f"SMA {slow}", sma(close, slow)),
    ]


def _macd_cross(
    prices: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> list[Indicator]:
    m = macd(prices["close"], fast, slow, signal)
    return [
        Indicator("MACD", m["macd"], panel="sub", hlines=(0,)),
        Indicator("Signal", m["signal"], panel="sub"),
    ]


def _rsi_reversion(
    prices: pd.DataFrame,
    window: int = 14,
    oversold: float = 30,
    overbought: float = 70,
) -> list[Indicator]:
    return [
        Indicator(
            f"RSI {window}",
            rsi(prices["close"], window),
            panel="sub",
            hlines=(oversold, overbought),
        )
    ]


def _bollinger(prices: pd.DataFrame, window: int = 20, k: float = 2.0) -> list[Indicator]:
    close = prices["close"]
    mid = close.rolling(window).mean()
    std = close.rolling(window).std()
    return [
        Indicator(f"Upper ({k}σ)", mid + k * std),
        Indicator(f"SMA {window}", mid),
        Indicator(f"Lower ({k}σ)", mid - k * std),
    ]


def _donchian(
    prices: pd.DataFrame, entry_window: int = 20, exit_window: int = 10
) -> list[Indicator]:
    upper = prices["high"].shift(1).rolling(entry_window).max()
    lower = prices["low"].shift(1).rolling(exit_window).min()
    return [
        Indicator(f"Donchian High ({entry_window})", upper),
        Indicator(f"Donchian Low ({exit_window})", lower),
    ]


def _vwap_reversion(
    prices: pd.DataFrame, window: int = 20, k: float = 1.5
) -> list[Indicator]:
    typical = (prices["high"] + prices["low"] + prices["close"]) / 3
    volume = prices["volume"]
    vwap = (typical * volume).rolling(window).sum() / volume.rolling(window).sum()
    std = (prices["close"] - vwap).rolling(window).std()
    return [
        Indicator(f"VWAP ({window})", vwap),
        Indicator(f"Lower ({k}σ)", vwap - k * std),
    ]


def _buy_hold(prices: pd.DataFrame) -> list[Indicator]:
    return []


def _faber_trend(prices: pd.DataFrame, window: int = 200) -> list[Indicator]:
    return [Indicator(f"SMA {window}", sma(prices["close"], window))]


_INDICATORS = {
    "Buy & Hold": _buy_hold,
    "Faber Trend Filter": _faber_trend,
    "SMA Cross": _sma_cross,
    "MACD Cross": _macd_cross,
    "RSI Mean Reversion": _rsi_reversion,
    "Bollinger Mean Reversion": _bollinger,
    "Donchian Breakout": _donchian,
    "VWAP Reversion": _vwap_reversion,
}


def indicators_for(
    strategy_name: str, prices: pd.DataFrame, **params
) -> list[Indicator]:
    return _INDICATORS[strategy_name](prices, **params)
