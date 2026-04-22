from __future__ import annotations

import pandas as pd
from backtesting import Strategy

from pytalk.indicators import rsi


def _rsi(values, window: int):
    return rsi(pd.Series(values), window).to_numpy()


class RsiReversion(Strategy):
    window = 14
    oversold = 30
    overbought = 70

    def init(self):
        self.rsi = self.I(_rsi, self.data.Close, self.window)

    def next(self):
        if self.rsi[-1] < self.oversold and not self.position:
            self.buy()
        elif self.rsi[-1] > self.overbought and self.position:
            self.position.close()
