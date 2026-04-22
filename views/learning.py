from __future__ import annotations

import streamlit as st

st.title("Learning — strategies")

st.markdown(
    """
The Backtest page offers six classic technical strategies. They fall into three families:

- **Trend-following** — profit when price keeps moving in one direction *(SMA Cross, MACD Cross)*
- **Mean-reversion** — profit when price returns to a central value *(RSI, Bollinger, VWAP)*
- **Breakout** — profit from sustained moves past a recent range *(Donchian)*

No strategy wins in every market. Parameter tuning and market regime matter as much as
the strategy choice. Always compare the backtest return against **Buy & Hold** to see
whether the strategy is actually adding value.
"""
)

st.divider()

with st.expander("SMA Cross — trend-following", expanded=True):
    st.markdown(
        """
**What it does.** Buys when a fast simple moving average crosses *above* a slow one
(the "golden cross"), sells when it crosses *below* ("death cross").

**How it works.** Two moving averages of closing prices. Their crossover is a simple,
lagging proxy for a change in trend direction.

**Parameters**
- **Fast SMA** *(default 20)* — shorter lookback, reacts quickly to new prices.
- **Slow SMA** *(default 50)* — longer baseline that represents the broader trend.

**Works best when…** the asset is in a sustained, directional trend (multi-month
bull or bear markets).

**Watch out for…** choppy, sideways markets — crossovers happen repeatedly, each
one a small losing trade. This is the classic whipsaw problem.
"""
    )

with st.expander("MACD Cross — trend-following with momentum"):
    st.markdown(
        """
**What it does.** Buys when the MACD line crosses *above* its signal line, sells
on the opposite cross.

**How it works.**
- **MACD line** = fast EMA − slow EMA (a measure of momentum)
- **Signal line** = EMA of the MACD line (smoother trigger)

Crossovers flag changes in the *rate of change* of price, not just direction.

**Parameters**
- **Fast EMA** *(12)* & **Slow EMA** *(26)* — the EMAs whose difference defines MACD.
- **Signal EMA** *(9)* — smoothing window that determines crossover timing.

**Works best when…** markets trend with medium-term momentum shifts. Usually gives
earlier signals than SMA Cross.

**Watch out for…** the signal line smooths but also delays entries — by the time
the crossover fires, part of the move is already gone. Also prone to whipsaws in
range-bound regimes.
"""
    )

with st.expander("RSI Mean Reversion — buy the dip"):
    st.markdown(
        """
**What it does.** Buys when RSI drops below the *oversold* threshold, closes the
position when RSI rises above *overbought*.

**How it works.** The Relative Strength Index compares the size of recent gains
to recent losses on a 0–100 scale. Low RSI = price has fallen too far too fast.

**Parameters**
- **Window** *(14)* — lookback period for the gain/loss smoothing.
- **Oversold** *(30)* — buy trigger.
- **Overbought** *(70)* — exit trigger.

**Works best when…** the asset oscillates around a stable fair value — range-bound
blue chips, index ETFs in calm regimes.

**Watch out for…** strong trends. RSI can stay below 30 for weeks during a crash
(the "falling knife") or above 70 during a rally. Mean-reversion in a trending
market means repeatedly fighting the tape.
"""
    )

with st.expander("Bollinger Mean Reversion — fade the extremes"):
    st.markdown(
        """
**What it does.** Buys when price touches the lower band, shorts when it touches
the upper band, and exits as price reverts to the middle band.

**How it works.** Bands are drawn at *±k standard deviations* around a moving
average. Under normal conditions, roughly 95% of price action stays inside 2σ
bands — touches of the outer bands suggest statistical extremes.

**Parameters**
- **Window** *(20)* — SMA period for the middle band *and* the volatility lookback.
- **Std deviations (k)** *(2.0)* — band width. Wider bands = fewer, higher-conviction signals.

**Works best when…** volatility is stationary and price mean-reverts — think
commodity pairs, index rebalancing, or consolidating stocks.

**Watch out for…** breakouts. When price "rides the band" (repeated touches
without reverting), this strategy shorts into a rally or longs into a crash.
Volatility regime shifts break the statistical assumption.
"""
    )

with st.expander("VWAP Reversion — volume-weighted anchor"):
    st.markdown(
        """
**What it does.** Buys when price falls a configurable distance *below* the rolling
Volume-Weighted Average Price, closes the position when price crosses back above VWAP.

**How it works.** VWAP weighs each bar's typical price *(H+L+C)/3* by its volume,
so heavily-traded prices pull the anchor more strongly than thin bars. Distance
from VWAP is a volume-aware measure of over-/under-pricing. The strategy enters
when the close is more than *k* standard deviations below VWAP and exits on
reversion through VWAP.

Two reasonable uses share the same signal:
- **Trend pullbacks** — in an uptrend, dips to VWAP are "cheap" entries that
  usually bounce.
- **Range fading** — in a sideways market, extreme distance from VWAP reverts.

**Parameters**
- **VWAP window** *(20)* — rolling lookback. On daily bars this is the equivalent
  of classic intraday VWAP (which resets each session).
- **Std deviations (k)** *(1.5)* — how far below VWAP price must go before entry.
  Smaller = more trades, lower conviction. Larger = fewer, stronger signals.

**Works best when…** the asset has meaningful, varying volume — individual
stocks, ETFs, liquid crypto. Volume is the whole point of VWAP.

**Watch out for…**
- Assets with no or flat volume (many indices like `^GSPC`, some futures) — VWAP
  collapses to a simple moving average and the strategy loses its edge.
- Downtrends — the strategy buys dips. Without a trend filter, it will repeatedly
  catch falling knives.
"""
    )

with st.expander("Donchian Breakout — Turtle-style trend capture"):
    st.markdown(
        """
**What it does.** Goes long when price breaks above the *N-day* high. Exits when
price drops below the *M-day* low. Pure price action — no averages, no oscillators.

**How it works.** Made famous by the 1980s Turtle Traders. The N-day high is the
highest close over the last N sessions; breaching it signals the start of a new
directional move. A shorter exit window gives back less profit on reversal.

**Parameters**
- **Entry window (N)** *(20)* — the breakout trigger lookback. Larger = fewer but stronger signals.
- **Exit window (M)** *(10)* — the trailing-stop lookback. Usually smaller than N.

**Works best when…** markets experience occasional, powerful directional moves —
commodities, trending equities, crypto in bull/bear legs.

**Watch out for…** prolonged sideways markets. Each false breakout is a small
loss, and they add up quickly. Also: Donchian buys *after* the breakout, so
you're never catching the absolute low.
"""
    )

st.divider()

st.markdown(
    """
### How to read the backtest results

- **Return [%]** — total strategy return over the backtest period.
- **Buy & Hold [%]** — what a passive investor would have earned. If your strategy
  underperforms this, the complexity isn't paying off.
- **Sharpe Ratio** — return per unit of volatility. Rough guide: < 1 is mediocre,
  1–2 is good, > 2 is suspicious (check for overfitting).
- **Max Drawdown [%]** — worst peak-to-trough loss along the way. A strategy
  with high return but 60% drawdown is psychologically very hard to trade.

**A note on overfitting.** Tuning parameters until backtest returns look great
almost always produces worse live results. A robust strategy works across a range
of parameter values, not just one. If a small parameter tweak changes the outcome
dramatically, the strategy is brittle.
"""
)
