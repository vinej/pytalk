from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from pytalk import get_prices
from pytalk.i18n import category_label, t
from pytalk.indicators import rsi, sma
from pytalk.universe import CATEGORIES, UNIVERSE

# Widget-state preservation is handled once in App.py.

st.title(t("screener.title"))

PERIODS = {"6m": 6, "1y": 12, "2y": 24, "5y": 60, "10y": 120}
MAX_LOOKBACK_MONTHS = PERIODS["10y"]


def _compute_row(ticker: str, category: str, end: date) -> dict | None:
    try:
        fetch_start = (
            pd.Timestamp(end) - pd.DateOffset(months=MAX_LOOKBACK_MONTHS)
        ).date() - timedelta(days=30)
        prices = get_prices(ticker, fetch_start, end)
    except Exception:
        return None
    if prices.empty or len(prices) < 20:
        return None

    close = prices["close"]                # price-return series (for indicators / risk)
    tr_close = prices["adj_close"]         # total-return series (for return columns)
    current = float(close.iloc[-1])
    current_tr = float(tr_close.iloc[-1])

    row: dict = {
        "Ticker": ticker,
        "Name": UNIVERSE[category].get(ticker, ""),
        "Type": category,
        "Price": current,
    }

    for period_name, months in PERIODS.items():
        target = pd.Timestamp(end) - pd.DateOffset(months=months)
        before = tr_close.loc[:target]
        if before.empty:
            row[period_name] = None
            continue
        past = float(before.iloc[-1])
        if past <= 0:
            row[period_name] = None
            continue
        row[period_name] = (current_tr / past - 1) * 100

    r = rsi(close, 14)
    row["RSI"] = float(r.iloc[-1]) if not r.empty and not pd.isna(r.iloc[-1]) else None

    s200 = sma(close, 200)
    last_s200 = s200.iloc[-1] if not s200.empty else None
    row["vs SMA200 %"] = (
        (current / float(last_s200) - 1) * 100
        if last_s200 is not None and not pd.isna(last_s200)
        else None
    )

    year_close = close.loc[pd.Timestamp(end) - pd.DateOffset(months=12):]
    if not year_close.empty:
        hi = float(year_close.max())
        lo = float(year_close.min())
        row["52w %"] = ((current - lo) / (hi - lo)) * 100 if hi > lo else None
        year_ret = year_close.pct_change().dropna()
        row["Vol %"] = (
            float(year_ret.std()) * np.sqrt(252) * 100 if len(year_ret) > 20 else None
        )
    else:
        row["52w %"] = None
        row["Vol %"] = None

    return row


def _run_screen(categories: list[str], end: date) -> pd.DataFrame:
    universe_items = [(t, c) for c in categories for t in UNIVERSE[c]]
    rows: list[dict] = []

    progress = st.progress(0.0)
    status = st.empty()
    for i, (ticker, category) in enumerate(universe_items):
        status.caption(
            t(
                "screener.loading_item",
                ticker=ticker,
                i=i + 1,
                total=len(universe_items),
            )
        )
        row = _compute_row(ticker, category, end)
        if row is not None:
            rows.append(row)
        progress.progress((i + 1) / len(universe_items))
    progress.empty()
    status.empty()

    return pd.DataFrame(rows)


with st.sidebar:
    categories = st.multiselect(
        t("screener.types"),
        CATEGORIES,
        default=["ETF"],
        format_func=category_label,
        key="screener_categories",
    )
    end = st.date_input(t("common.end_date"), value=date.today(), key="screener_end")
    run = st.button(t("screener.run"), type="primary")
    if st.button(t("common.clear_results")):
        st.session_state.pop("_screener_df", None)
        st.rerun()

if run:
    if not categories:
        st.warning(t("screener.pick_type"))
        st.stop()
    df = _run_screen(categories, end)
    st.session_state["_screener_df"] = df
    st.session_state["_screener_meta"] = {
        "categories": categories,
        "end": end,
        "count": len(df),
    }

if "_screener_df" not in st.session_state:
    st.info(t("screener.intro"))
    st.stop()

df: pd.DataFrame = st.session_state["_screener_df"]
meta = st.session_state.get("_screener_meta", {})

if df.empty:
    st.warning(t("screener.no_data"))
    st.stop()

st.caption(
    t(
        "screener.loaded",
        count=meta.get("count", len(df)),
        cats=", ".join(category_label(c) for c in meta.get("categories", [])),
        end=meta.get("end", end),
    )
)

st.subheader(t("screener.filters"))


def _range_filter(
    label: str,
    lo_bound: float,
    hi_bound: float,
    step: float,
    key: str,
    fmt: str = "%.1f",
) -> tuple[float, float]:
    """Two number inputs + a slider, all kept in sync via callbacks."""
    min_k = f"{key}_min"
    max_k = f"{key}_max"
    slider_k = f"{key}_slider"

    if min_k not in st.session_state:
        st.session_state[min_k] = float(lo_bound)
        st.session_state[max_k] = float(hi_bound)
        st.session_state[slider_k] = (float(lo_bound), float(hi_bound))

    def _from_numbers():
        mn = float(st.session_state[min_k])
        mx = float(st.session_state[max_k])
        if mn > mx:
            mn, mx = mx, mn
            st.session_state[min_k] = mn
            st.session_state[max_k] = mx
        st.session_state[slider_k] = (mn, mx)

    def _from_slider():
        mn, mx = st.session_state[slider_k]
        st.session_state[min_k] = float(mn)
        st.session_state[max_k] = float(mx)

    st.markdown(f"**{label}**")
    c1, c2 = st.columns(2)
    c1.number_input(
        t("screener.min"),
        min_value=float(lo_bound),
        max_value=float(hi_bound),
        step=float(step),
        key=min_k,
        on_change=_from_numbers,
        format=fmt,
        label_visibility="collapsed",
    )
    c2.number_input(
        t("screener.max"),
        min_value=float(lo_bound),
        max_value=float(hi_bound),
        step=float(step),
        key=max_k,
        on_change=_from_numbers,
        format=fmt,
        label_visibility="collapsed",
    )
    st.slider(
        label,
        float(lo_bound),
        float(hi_bound),
        step=float(step),
        key=slider_k,
        on_change=_from_slider,
        label_visibility="collapsed",
    )
    return float(st.session_state[min_k]), float(st.session_state[max_k])


filter_cols = st.columns(3)
with filter_cols[0]:
    st.markdown(f"### {t('screener.returns')}")
    r6m = _range_filter("6m", -100.0, 2000.0, 1.0, "r6m")
    r1y = _range_filter("1y", -100.0, 2000.0, 1.0, "r1y")
    r2y = _range_filter("2y", -100.0, 2000.0, 1.0, "r2y")
    r5y = _range_filter("5y", -100.0, 5000.0, 10.0, "r5y")
    r10y = _range_filter("10y", -100.0, 10000.0, 10.0, "r10y")

with filter_cols[1]:
    st.markdown(f"### {t('screener.indicators')}")
    rsi_r = _range_filter("RSI(14)", 0.0, 100.0, 1.0, "rsi")
    sma_r = _range_filter(t("screener.vs_sma200"), -80.0, 200.0, 1.0, "sma200")
    pos_r = _range_filter(t("screener.pos_52w"), 0.0, 100.0, 1.0, "pos52w")

with filter_cols[2]:
    st.markdown(f"### {t('screener.risk')}")
    vol_r = _range_filter(t("screener.annual_vol"), 0.0, 300.0, 1.0, "vol")
    exclude_na = st.checkbox(
        t("screener.exclude_na"),
        value=False,
        help=t("screener.exclude_na_help"),
    )


def _apply(
    frame: pd.DataFrame, col: str, rng: tuple[float, float], full: tuple[float, float]
) -> pd.DataFrame:
    if rng == full:
        return frame
    lo, hi = rng
    mask = (frame[col] >= lo) & (frame[col] <= hi)
    if not exclude_na:
        mask = mask | frame[col].isna()
    return frame[mask]


filtered = df.copy()
filtered = _apply(filtered, "6m", r6m, (-100.0, 2000.0))
filtered = _apply(filtered, "1y", r1y, (-100.0, 2000.0))
filtered = _apply(filtered, "2y", r2y, (-100.0, 2000.0))
filtered = _apply(filtered, "5y", r5y, (-100.0, 5000.0))
filtered = _apply(filtered, "10y", r10y, (-100.0, 10000.0))
filtered = _apply(filtered, "RSI", rsi_r, (0.0, 100.0))
filtered = _apply(filtered, "vs SMA200 %", sma_r, (-80.0, 200.0))
filtered = _apply(filtered, "52w %", pos_r, (0.0, 100.0))
filtered = _apply(filtered, "Vol %", vol_r, (0.0, 300.0))

sort_col = st.selectbox(
    t("screener.sort_by"),
    ["Ticker", "Type", "Price", "6m", "1y", "2y", "5y", "10y", "RSI", "vs SMA200 %", "52w %", "Vol %"],
    index=0,
)
descending = st.checkbox(t("screener.descending"), value=False)
filtered = filtered.sort_values(
    sort_col, ascending=not descending, na_position="last"
).reset_index(drop=True)

st.subheader(t("screener.results", shown=len(filtered), total=len(df)))
st.dataframe(
    filtered,
    width="stretch",
    hide_index=True,
    column_config={
        "Price": st.column_config.NumberColumn(format="%.2f"),
        "6m": st.column_config.NumberColumn("6m %", format="%+.2f"),
        "1y": st.column_config.NumberColumn("1y %", format="%+.2f"),
        "2y": st.column_config.NumberColumn("2y %", format="%+.2f"),
        "5y": st.column_config.NumberColumn("5y %", format="%+.2f"),
        "10y": st.column_config.NumberColumn("10y %", format="%+.2f"),
        "RSI": st.column_config.NumberColumn(format="%.1f"),
        "vs SMA200 %": st.column_config.NumberColumn(format="%+.2f"),
        "52w %": st.column_config.NumberColumn(format="%.1f"),
        "Vol %": st.column_config.NumberColumn(format="%.1f"),
    },
)
