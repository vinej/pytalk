from __future__ import annotations

import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover


def _macd_line(values, fast: int, slow: int):
    close = pd.Series(values)
    return (
        close.ewm(span=fast, adjust=False).mean()
        - close.ewm(span=slow, adjust=False).mean()
    ).to_numpy()


def _signal_line(values, fast: int, slow: int, signal: int):
    close = pd.Series(values)
    macd = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    return macd.ewm(span=signal, adjust=False).mean().to_numpy()


class MacdCross(Strategy):
    fast = 12
    slow = 26
    signal = 9

    def init(self):
        close = self.data.Close
        self.macd = self.I(_macd_line, close, self.fast, self.slow)
        self.signal_line = self.I(_signal_line, close, self.fast, self.slow, self.signal)

    def next(self):
        if crossover(self.macd, self.signal_line):
            self.position.close()
            self.buy()
        elif crossover(self.signal_line, self.macd):
            self.position.close()
            self.sell()
