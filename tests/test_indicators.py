import numpy as np
import pandas as pd

from pytalk.indicators import add_indicators, rsi


def _ohlcv(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    close = 100 + rng.standard_normal(n).cumsum()
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=idx,
    )


def test_rsi_bounded():
    df = _ohlcv()
    values = rsi(df["close"]).dropna()
    assert values.between(0, 100).all()


def test_add_indicators_columns():
    df = add_indicators(_ohlcv())
    for col in ["sma_20", "sma_50", "ema_20", "rsi_14", "macd", "signal", "hist"]:
        assert col in df.columns
