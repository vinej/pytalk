from __future__ import annotations

import pandas as pd
from backtesting import Strategy


def _sma(values, window: int):
    return pd.Series(values).rolling(window).mean()


class FaberTrend(Strategy):
    """Faber 2007-style trend filter: hold when close > N-period SMA, cash otherwise.

    On daily bars, window=200 ≈ Faber's 10-month rule. Reduces drawdowns
    materially vs buy-and-hold with only modest return give-up.
    """

    window = 200

    def init(self):
        self.sma = self.I(_sma, self.data.Close, self.window)

    def next(self):
        price = self.data.Close[-1]
        if not self.position and price > self.sma[-1]:
            self.buy()
        elif self.position.is_long and price < self.sma[-1]:
            self.position.close()
