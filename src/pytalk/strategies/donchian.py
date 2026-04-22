from __future__ import annotations

import pandas as pd
from backtesting import Strategy


def _rolling_high(values, window: int):
    return pd.Series(values).shift(1).rolling(window).max().to_numpy()


def _rolling_low(values, window: int):
    return pd.Series(values).shift(1).rolling(window).min().to_numpy()


class DonchianBreakout(Strategy):
    """Turtle-style: enter long on N-day high breakout, exit on M-day low breakdown."""

    entry_window = 20
    exit_window = 10

    def init(self):
        high = self.data.High
        low = self.data.Low
        self.upper = self.I(_rolling_high, high, self.entry_window)
        self.lower = self.I(_rolling_low, low, self.exit_window)

    def next(self):
        price = self.data.Close[-1]
        if not self.position and price > self.upper[-1]:
            self.buy()
        elif self.position.is_long and price < self.lower[-1]:
            self.position.close()
