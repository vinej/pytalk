from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pytalk import get_prices
from pytalk.data import get_currency
from pytalk.strategies import STRATEGIES
from pytalk.strategies.display import indicators_for
from pytalk.strategies.signals import signals_for
from pytalk.universe import CATEGORIES, OTHER, UNIVERSE, label, tickers

# Preserve widget state across page navigation
for _k in list(st.session_state.keys()):
    st.session_state[_k] = st.session_state[_k]

with st.sidebar:
    category = st.selectbox(
        "Type",
        CATEGORIES,
        index=CATEGORIES.index("Stock"),
        key="analysis_category",
    )
    options = tickers(category) + [OTHER]
    choice = st.selectbox(
        "Ticker",
        options,
        format_func=lambda s: label(category, s),
        key=f"analysis_ticker_{category}",
    )
    if choice == OTHER:
        ticker = st.text_input(
            "Custom ticker",
            placeholder="e.g. NESN.SW, 0700.HK",
            key="analysis_custom_ticker",
        ).strip().upper()
    else:
        ticker = choice
    lookback_days = st.slider(
        "Lookback (days)", 30, 1825, 365, key="analysis_lookback"
    )
    end = st.date_input("End date", value=date.today(), key="analysis_end")
    start = end - timedelta(days=lookback_days)
    strategy_name = st.selectbox(
        "Strategy indicators",
        list(STRATEGIES.keys()),
        key="analysis_strategy",
    )
    show_indicators = st.checkbox(
        "Show indicators", value=True, key="analysis_show_indicators"
    )

if not ticker:
    st.info("Pick a ticker to begin.")
    st.stop()


@st.cache_data(ttl=86400, show_spinner=False)
def _currency_for(tkr: str) -> str:
    return get_currency(tkr)


_currency = _currency_for(ticker)
_name = UNIVERSE.get(category, {}).get(ticker, "")
_title = f"Analysis for {ticker}"
if _name:
    _title += f" - {_name}"
if _currency:
    _title += f" in {_currency}"
st.title(_title)

with st.spinner(f"Loading {ticker}…"):
    df = get_prices(ticker, start, end)

if df.empty:
    st.error(f"No data for {ticker} in the selected range.")
    st.stop()

PERF_PERIODS = [("6m", 6), ("1y", 12), ("2y", 24), ("5y", 60), ("10y", 120)]
_perf_start = (
    pd.Timestamp(end) - pd.DateOffset(months=PERF_PERIODS[-1][1])
).date() - timedelta(days=30)
with st.spinner("Loading past performance…"):
    perf_prices = get_prices(ticker, _perf_start, end)


def _compact_metric(col, label: str, value: str, ret: float | None = None) -> None:
    color = ""
    if ret is not None:
        if ret > 0:
            color = "color:#2ca02c;"
        elif ret < 0:
            color = "color:#d62728;"
    col.markdown(
        f'<div style="text-align:center; padding:0.15em 0;">'
        f'<div style="font-size:0.75em; color:#888;">{label}</div>'
        f'<div style="font-size:1em; font-weight:600; {color}">{value}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


st.subheader("Past performance")
if perf_prices.empty or len(perf_prices) < 2:
    st.caption("No historical data available.")
else:
    current_price = perf_prices["close"].iloc[-1]

    cols = st.columns(len(PERF_PERIODS))
    for (period_label, months), col in zip(PERF_PERIODS, cols):
        target = pd.Timestamp(end) - pd.DateOffset(months=months)
        before = perf_prices.loc[:target]
        if before.empty:
            _compact_metric(col, period_label, "—")
            continue
        past_price = float(before["close"].iloc[-1])
        if past_price <= 0:
            _compact_metric(col, period_label, "—")
            continue
        ret = (current_price / past_price - 1) * 100
        _compact_metric(col, period_label, f"{ret:+.2f}%", ret=ret)

    year_cols = st.columns(5)
    years = [end.year - i for i in range(5)]
    for i, y in enumerate(years):
        start_ts = pd.Timestamp(year=y - 1, month=12, day=31)
        end_ts = (
            pd.Timestamp(year=y, month=12, day=31)
            if y < end.year
            else pd.Timestamp(end)
        )
        before_start = perf_prices.loc[:start_ts]
        before_end = perf_prices.loc[:end_ts]
        year_label = f"{y} YTD" if y == end.year else str(y)
        if before_start.empty or before_end.empty:
            _compact_metric(year_cols[i], year_label, "—")
            continue
        s_close = float(before_start["close"].iloc[-1])
        e_close = float(before_end["close"].iloc[-1])
        if s_close <= 0:
            _compact_metric(year_cols[i], year_label, "—")
            continue
        year_ret = (e_close / s_close - 1) * 100
        _compact_metric(year_cols[i], year_label, f"{year_ret:+.2f}%", ret=year_ret)

indicators = indicators_for(strategy_name, df) if show_indicators else []
price_overlays = [ind for ind in indicators if ind.panel == "price"]
sub_indicators = [ind for ind in indicators if ind.panel == "sub"]

metrics = [("Close", f"{df['close'].iloc[-1]:.2f}")]
for ind in indicators[:3]:
    value = ind.series.dropna()
    metrics.append((ind.name, f"{value.iloc[-1]:.2f}" if not value.empty else "—"))
cols = st.columns(len(metrics))
for col, (name, value) in zip(cols, metrics):
    col.metric(name, value)

has_sub = bool(sub_indicators)
rows = 3 if has_sub else 2
row_heights = [0.65, 0.2, 0.15] if has_sub else [0.8, 0.2]
subplot_titles = ["Price", "Volume"] + ([strategy_name] if has_sub else [])

fig = make_subplots(
    rows=rows,
    cols=1,
    shared_xaxes=True,
    row_heights=row_heights,
    vertical_spacing=0.03,
    subplot_titles=subplot_titles,
)

fig.add_trace(
    go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name=ticker,
    ),
    row=1,
    col=1,
)

for ind in price_overlays:
    fig.add_trace(go.Scatter(x=df.index, y=ind.series, name=ind.name), row=1, col=1)

if show_indicators:
    signals = signals_for(strategy_name, df)
    buys = signals[signals == "B"]
    sells = signals[signals == "S"]
    span = float((df["high"].max() - df["low"].min()) or 1.0)
    offset = span * 0.02
    if not buys.empty:
        fig.add_trace(
            go.Scatter(
                x=buys.index,
                y=df.loc[buys.index, "low"] - offset,
                mode="markers+text",
                marker=dict(symbol="triangle-up", size=11, color="#2ca02c"),
                text=["B"] * len(buys),
                textposition="bottom center",
                textfont=dict(color="black", size=16, family="Arial Black"),
                name="Buy",
                hovertemplate="Buy<br>%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )
    if not sells.empty:
        fig.add_trace(
            go.Scatter(
                x=sells.index,
                y=df.loc[sells.index, "high"] + offset,
                mode="markers+text",
                marker=dict(symbol="triangle-down", size=11, color="#d62728"),
                text=["S"] * len(sells),
                textposition="top center",
                textfont=dict(color="black", size=16, family="Arial Black"),
                name="Sell",
                hovertemplate="Sell<br>%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume"), row=2, col=1)

if has_sub:
    sub_row = 3
    for ind in sub_indicators:
        fig.add_trace(go.Scatter(x=df.index, y=ind.series, name=ind.name), row=sub_row, col=1)
    seen_hlines: set[float] = set()
    for ind in sub_indicators:
        for h in ind.hlines:
            if h in seen_hlines:
                continue
            seen_hlines.add(h)
            fig.add_hline(y=h, line_dash="dash", line_color="gray", row=sub_row, col=1)

fig.update_layout(height=800, xaxis_rangeslider_visible=False, showlegend=True)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Raw data"):
    st.dataframe(df.tail(100))
