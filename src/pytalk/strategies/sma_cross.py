from __future__ import annotations

from backtesting import Strategy
from backtesting.lib import crossover

import pandas as pd


def _sma(values, window: int):
    return pd.Series(values).rolling(window).mean()


class SmaCross(Strategy):
    fast = 20
    slow = 50

    def init(self):
        close = self.data.Close
        self.sma_fast = self.I(_sma, close, self.fast)
        self.sma_slow = self.I(_sma, close, self.slow)

    def next(self):
        if crossover(self.sma_fast, self.sma_slow):
            self.position.close()
            self.buy()
        elif crossover(self.sma_slow, self.sma_fast):
            self.position.close()
            self.sell()
