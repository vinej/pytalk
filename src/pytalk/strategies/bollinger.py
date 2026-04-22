from __future__ import annotations

import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover


def _upper(values, window: int, k: float):
    s = pd.Series(values)
    return (s.rolling(window).mean() + k * s.rolling(window).std()).to_numpy()


def _lower(values, window: int, k: float):
    s = pd.Series(values)
    return (s.rolling(window).mean() - k * s.rolling(window).std()).to_numpy()


def _mid(values, window: int):
    return pd.Series(values).rolling(window).mean().to_numpy()


class BollingerReversion(Strategy):
    """Buy touches of the lower band, exit on mid-band reversion; short the upper band."""

    window = 20
    k = 2.0

    def init(self):
        close = self.data.Close
        self.upper = self.I(_upper, close, self.window, self.k)
        self.lower = self.I(_lower, close, self.window, self.k)
        self.mid = self.I(_mid, close, self.window)

    def next(self):
        price = self.data.Close[-1]
        if not self.position:
            if price < self.lower[-1]:
                self.buy()
            elif price > self.upper[-1]:
                self.sell()
        elif self.position.is_long and crossover(self.data.Close, self.mid):
            self.position.close()
        elif self.position.is_short and crossover(self.mid, self.data.Close):
            self.position.close()
