import numpy as np
import pandas as pd

from pytalk.backtest import run_backtest
from pytalk.strategies import SmaCross


def _trending_ohlcv(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    trend = np.linspace(100, 160, n)
    noise = rng.standard_normal(n) * 0.5
    close = trend + noise
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=idx,
    )


def test_sma_cross_runs():
    result = run_backtest(_trending_ohlcv(), SmaCross, fast=10, slow=30)
    assert "Return [%]" in result.stats.index
    assert not result.equity_curve.empty
