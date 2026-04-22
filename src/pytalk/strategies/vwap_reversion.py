from __future__ import annotations

import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover


def _vwap(typical_price, volume, window: int):
    tp = pd.Series(typical_price)
    v = pd.Series(volume)
    return ((tp * v).rolling(window).sum() / v.rolling(window).sum()).to_numpy()


def _lower_band(typical_price, volume, close, window: int, k: float):
    tp = pd.Series(typical_price)
    v = pd.Series(volume)
    c = pd.Series(close)
    vwap = (tp * v).rolling(window).sum() / v.rolling(window).sum()
    std = (c - vwap).rolling(window).std()
    return (vwap - k * std).to_numpy()


class VwapReversion(Strategy):
    """Buy when price falls a chosen distance below rolling VWAP, exit on reversion."""

    window = 20
    k = 1.5

    def init(self):
        high = self.data.High
        low = self.data.Low
        close = self.data.Close
        volume = self.data.Volume
        typical_price = (high + low + close) / 3

        self.vwap = self.I(_vwap, typical_price, volume, self.window)
        self.lower = self.I(_lower_band, typical_price, volume, close, self.window, self.k)

    def next(self):
        if not self.position and self.data.Close[-1] < self.lower[-1]:
            self.buy()
        elif self.position.is_long and crossover(self.data.Close, self.vwap):
            self.position.close()
