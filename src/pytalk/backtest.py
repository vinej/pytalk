from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy


@dataclass
class BacktestResult:
    stats: pd.Series
    equity_curve: pd.DataFrame
    trades: pd.DataFrame


@dataclass
class PortfolioBacktestResult:
    equity: pd.Series
    per_ticker: dict[str, BacktestResult] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    @property
    def stats(self) -> pd.Series:
        eq = self.equity.dropna()
        if eq.empty or len(eq) < 2:
            return pd.Series(dtype=float)
        returns = eq.pct_change().dropna()
        total_return = (eq.iloc[-1] / eq.iloc[0] - 1) * 100
        std = returns.std()
        sharpe = float((returns.mean() / std) * np.sqrt(252)) if std > 0 else 0.0
        roll_max = eq.cummax()
        max_dd = float(((eq / roll_max) - 1).min() * 100)
        return pd.Series(
            {
                "Return [%]": float(total_return),
                "Sharpe Ratio": sharpe,
                "Max. Drawdown [%]": max_dd,
                "Start Equity": float(eq.iloc[0]),
                "Final Equity": float(eq.iloc[-1]),
            }
        )


def _to_backtesting_frame(df: pd.DataFrame) -> pd.DataFrame:
    """backtesting.py expects capitalized OHLCV columns and a DatetimeIndex."""
    out = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"Missing columns for backtest: {missing}")
    return out[required].dropna()


def run_backtest(
    prices: pd.DataFrame,
    strategy: type[Strategy],
    *,
    cash: float = 10_000,
    commission: float = 0.002,
    **strategy_params: Any,
) -> BacktestResult:
    data = _to_backtesting_frame(prices)
    if strategy_params:
        strategy = type(strategy.__name__, (strategy,), strategy_params)
    bt = Backtest(data, strategy, cash=cash, commission=commission, finalize_trades=True)
    stats = bt.run()
    return BacktestResult(
        stats=stats.drop(labels=["_strategy", "_equity_curve", "_trades"], errors="ignore"),
        equity_curve=stats["_equity_curve"],
        trades=stats["_trades"],
    )


def run_portfolio_backtest(
    prices_by_ticker: dict[str, pd.DataFrame],
    weights: dict[str, float],
    strategy: type[Strategy],
    *,
    cash: float = 10_000,
    commission: float = 0.002,
    **strategy_params: Any,
) -> PortfolioBacktestResult:
    """Run `strategy` per ticker, combine equity curves by weight."""
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Weights must sum to a positive value")
    normalized = {t: w / total_weight for t, w in weights.items()}

    per_ticker: dict[str, BacktestResult] = {}
    equity_curves: dict[str, pd.Series] = {}
    skipped: list[str] = []

    for ticker, prices in prices_by_ticker.items():
        if ticker not in normalized:
            continue
        if prices is None or prices.empty:
            skipped.append(ticker)
            continue
        allocation = cash * normalized[ticker]
        try:
            result = run_backtest(
                prices,
                strategy,
                cash=allocation,
                commission=commission,
                **strategy_params,
            )
        except Exception:
            skipped.append(ticker)
            continue
        per_ticker[ticker] = result
        equity_curves[ticker] = result.equity_curve["Equity"]

    if not equity_curves:
        raise ValueError("No usable price data for any holding in the portfolio")

    equity_df = pd.concat(equity_curves, axis=1).sort_index().dropna()
    combined = equity_df.sum(axis=1)

    return PortfolioBacktestResult(
        equity=combined,
        per_ticker=per_ticker,
        weights=normalized,
        skipped=skipped,
    )
