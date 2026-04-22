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


def _sma_cross(prices: pd.DataFrame) -> list[Indicator]:
    close = prices["close"]
    return [
        Indicator("SMA 20", sma(close, 20)),
        Indicator("SMA 50", sma(close, 50)),
    ]


def _macd_cross(prices: pd.DataFrame) -> list[Indicator]:
    m = macd(prices["close"], 12, 26, 9)
    return [
        Indicator("MACD", m["macd"], panel="sub", hlines=(0,)),
        Indicator("Signal", m["signal"], panel="sub"),
    ]


def _rsi_reversion(prices: pd.DataFrame) -> list[Indicator]:
    return [Indicator("RSI 14", rsi(prices["close"], 14), panel="sub", hlines=(30, 70))]


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


_INDICATORS = {
    "SMA Cross": _sma_cross,
    "MACD Cross": _macd_cross,
    "RSI Mean Reversion": _rsi_reversion,
    "Bollinger Mean Reversion": _bollinger,
    "Donchian Breakout": _donchian,
    "VWAP Reversion": _vwap_reversion,
}


def indicators_for(strategy_name: str, prices: pd.DataFrame) -> list[Indicator]:
    return _INDICATORS[strategy_name](prices)
