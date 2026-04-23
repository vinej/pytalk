from pytalk.strategies.bollinger import BollingerReversion
from pytalk.strategies.buy_hold import BuyHold
from pytalk.strategies.donchian import DonchianBreakout
from pytalk.strategies.faber_trend import FaberTrend
from pytalk.strategies.macd_cross import MacdCross
from pytalk.strategies.rsi_reversion import RsiReversion
from pytalk.strategies.sma_cross import SmaCross
from pytalk.strategies.vwap_reversion import VwapReversion

STRATEGIES = {
    "Buy & Hold": BuyHold,
    "Faber Trend Filter": FaberTrend,
    "SMA Cross": SmaCross,
    "MACD Cross": MacdCross,
    "RSI Mean Reversion": RsiReversion,
    "Bollinger Mean Reversion": BollingerReversion,
    "Donchian Breakout": DonchianBreakout,
    "VWAP Reversion": VwapReversion,
}

__all__ = [
    "BuyHold",
    "FaberTrend",
    "SmaCross",
    "MacdCross",
    "RsiReversion",
    "BollingerReversion",
    "DonchianBreakout",
    "VwapReversion",
    "STRATEGIES",
]
