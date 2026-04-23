from __future__ import annotations

from backtesting import Strategy


class BuyHold(Strategy):
    """Buy on the first bar, hold to the end. No parameters, no indicators."""

    def init(self):
        pass

    def next(self):
        if not self.position:
            self.buy()
