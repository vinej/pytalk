"""Analysis view — chart a single ticker or a portfolio.

Two modes (chosen by sidebar radio, drives the rest of the page):

    Single ticker  → fetch prices, draw candlestick + volume, optional indicators
    Portfolio      → load holdings, build either a "real value" or "rebased to 100"
                     equity curve, show holdings P&L table, draw line chart

Portfolio mode has two sub-flavors:
    has_positions  → every holding has shares + buy_date → real-dollar value series
    legacy         → at least one holding lacks shares → fall back to weight-based
                     rebased-to-100 series with a warning

The page also renders a Past Performance grid (TR vs PR returns over fixed windows
+ calendar years), and an optional LLM blurb (validate portfolio / describe ticker).
See ARCHITECTURE.md for the broader picture.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pytalk import get_prices
from pytalk.auth import current_user
from pytalk.custom_tickers import (
    add_ticker,
    combined_label,
    combined_symbols,
    lookup_name,
)
from pytalk.data import detect_category, get_currency
from pytalk.i18n import category_label, t
from pytalk.indicators import rsi, sma
from pytalk.llm import build_describe_ticker_prompt, build_validate_portfolio_prompt
from pytalk.portfolios import get_portfolio, list_portfolios
from pytalk.ui import render_llm_block
from pytalk.universe import CATEGORIES, OTHER, label, tickers

CURRENT_USER = current_user()

_SOURCE_LABELS = {
    "Single ticker": "common.source_single",
    "Portfolio": "common.source_portfolio",
}

# ── Sidebar: source + ticker/portfolio + lookback + chart toggles ───────────
with st.sidebar:
    source = st.radio(
        t("common.source"),
        ["Single ticker", "Portfolio"],
        horizontal=True,
        format_func=lambda s: t(_SOURCE_LABELS[s]),
        key="analysis_source",
    )

    ticker: str | None = None
    category: str | None = None
    portfolio_name: str | None = None

    if source == "Single ticker":
        category = st.selectbox(
            t("common.type"),
            CATEGORIES,
            index=CATEGORIES.index("ETF"),
            format_func=category_label,
            key="analysis_category",
        )
        _symbols = combined_symbols(CURRENT_USER, category)
        options = _symbols + [OTHER]
        _default_ticker = (
            "CASH.TO" if category == "ETF" and "CASH.TO" in _symbols else _symbols[0]
        )
        _default_idx = _symbols.index(_default_ticker) if _default_ticker in _symbols else 0
        choice = st.selectbox(
            t("common.ticker"),
            options,
            index=_default_idx,
            format_func=lambda s: combined_label(CURRENT_USER, category, s),
            key=f"analysis_ticker_{category}",
        )
        if choice == OTHER:
            ticker = st.text_input(
                t("common.custom_ticker"),
                placeholder=t("common.ticker_placeholder"),
                key="analysis_custom_ticker",
            ).strip().upper()
        else:
            ticker = choice
    else:
        portfolio_names = list_portfolios(CURRENT_USER)
        if not portfolio_names:
            st.warning(t("common.no_portfolios"))
        else:
            portfolio_name = st.selectbox(
                t("common.portfolio"), portfolio_names, key="analysis_portfolio"
            )

    lookback_days = st.slider(
        t("common.lookback"), 30, 3650, 365, key="analysis_lookback"
    )
    end = st.date_input(t("common.end_date"), value=date.today(), key="analysis_end")
    start = end - timedelta(days=lookback_days)
    show_volatility = st.checkbox(
        t("common.show_volatility"), value=False, key="analysis_show_volatility"
    )
    if show_volatility:
        vol_window = st.slider(
            t("common.vol_window"), 5, 252, 21, key="analysis_vol_window"
        )
    else:
        vol_window = 21

    show_smas = st.checkbox(
        t("common.show_smas"), value=False, key="analysis_show_smas"
    )
    if show_smas:
        sma_fast_window = st.slider(
            t("backtest.sma_fast"), 5, 250, 50, key="analysis_ref_sma_fast"
        )
        sma_slow_window = st.slider(
            t("backtest.sma_slow"), 20, 500, 200, key="analysis_ref_sma_slow"
        )
    else:
        sma_fast_window, sma_slow_window = 50, 200

    show_rsi = st.checkbox(
        t("common.show_rsi"), value=False, key="analysis_show_rsi"
    )
    if show_rsi:
        rsi_window = st.slider(
            t("backtest.rsi_window"), 2, 50, 14, key="analysis_ref_rsi_window"
        )
    else:
        rsi_window = 14

    show_legend = st.checkbox(
        t("common.show_legend"), value=True, key="analysis_show_legend"
    )

is_portfolio = source == "Portfolio"


@st.cache_data(ttl=86400, show_spinner=False)
def _currency_for(tkr: str) -> str:
    return get_currency(tkr)


@st.cache_data(ttl=86400, show_spinner=False)
def _detect_category_cached(tkr: str) -> str:
    return detect_category(tkr)


def _build_portfolio_series(
    weights: dict[str, float], s: date, e: date
) -> pd.DataFrame:
    """Weighted buy-and-hold equity curve for a portfolio, rebased to 100 at start."""
    closes: dict[str, pd.Series] = {}
    adjs: dict[str, pd.Series] = {}
    for tkr in weights:
        prices = get_prices(tkr, s, e)
        if prices.empty:
            continue
        closes[tkr] = prices["close"]
        adjs[tkr] = prices["adj_close"]
    if not closes:
        return pd.DataFrame()

    closes_df = pd.DataFrame(closes).sort_index().ffill().dropna()
    adjs_df = pd.DataFrame(adjs).sort_index().ffill().dropna()
    if closes_df.empty:
        return pd.DataFrame()

    w = pd.Series({t: weights[t] for t in closes_df.columns})
    w = w / w.sum()
    closes_norm = (closes_df / closes_df.iloc[0]) * 100
    adjs_norm = (adjs_df / adjs_df.iloc[0]) * 100
    combined_close = (closes_norm * w).sum(axis=1)
    combined_adj = (adjs_norm * w).sum(axis=1)

    return pd.DataFrame(
        {
            "open": combined_close,
            "high": combined_close,
            "low": combined_close,
            "close": combined_close,
            "adj_close": combined_adj,
            "volume": 0,
        }
    )


def _build_portfolio_value_series(
    holdings, s: date, e: date
) -> pd.DataFrame:
    """Real dollar value series = sum(shares × close) per day for shares-based holdings.

    Holdings without shares are skipped. Returns OHLC-shaped df where every
    OHLC field equals the day's portfolio value. Empty df if no usable holdings.
    """
    closes: dict[str, pd.Series] = {}
    adjs: dict[str, pd.Series] = {}
    shares_map: dict[str, float] = {}
    for h in holdings:
        if h.shares <= 0:
            continue
        prices = get_prices(h.ticker, s, e)
        if prices.empty:
            continue
        closes[h.ticker] = prices["close"]
        adjs[h.ticker] = prices["adj_close"]
        shares_map[h.ticker] = float(h.shares)
    if not closes:
        return pd.DataFrame()

    closes_df = pd.DataFrame(closes).sort_index().ffill().dropna()
    adjs_df = pd.DataFrame(adjs).sort_index().ffill().dropna()
    if closes_df.empty:
        return pd.DataFrame()

    sh = pd.Series(shares_map)
    combined_close = (closes_df * sh).sum(axis=1)
    combined_adj = (adjs_df * sh).sum(axis=1)
    return pd.DataFrame(
        {
            "open": combined_close,
            "high": combined_close,
            "low": combined_close,
            "close": combined_close,
            "adj_close": combined_adj,
            "volume": 0,
        }
    )


def _holdings_pnl(holdings, end_d: date) -> tuple[list[dict], dict[str, float]]:
    """Per-holding P&L as of end_d. Returns (rows, current_values_by_ticker).

    Skips holdings without shares or buy_date. Buy price is the first available
    close on/after buy_date; current price is the last close on/before end_d.

    `current_values_by_ticker` is reused upstream to derive *current* portfolio
    weights (vs the static target weight stored on each Holding).
    """
    rows: list[dict] = []
    values: dict[str, float] = {}
    for h in holdings:
        if h.shares <= 0 or not h.buy_date:
            continue
        try:
            buy_d = date.fromisoformat(h.buy_date)
        except (ValueError, TypeError):
            continue

        prices = get_prices(h.ticker, buy_d, end_d)
        if prices.empty:
            rows.append({
                "ticker": h.ticker,
                "shares": h.shares,
                "buy_date": h.buy_date,
                "buy_price": None,
                "current_price": None,
                "cost_basis": None,
                "current_value": None,
                "pnl": None,
                "pnl_pct": None,
            })
            continue

        buy_price = float(prices["close"].iloc[0])
        current_price = float(prices["close"].iloc[-1])
        cost = h.shares * buy_price
        value = h.shares * current_price
        pnl = value - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else None

        rows.append({
            "ticker": h.ticker,
            "shares": h.shares,
            "buy_date": h.buy_date,
            "buy_price": buy_price,
            "current_price": current_price,
            "cost_basis": cost,
            "current_value": value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })
        values[h.ticker] = value
    return rows, values


# ── Load data: portfolio path vs single-ticker path ─────────────────────────
if is_portfolio:
    if not portfolio_name:
        st.info(t("common.pick_portfolio"))
        st.stop()
    portfolio = get_portfolio(CURRENT_USER, portfolio_name)
    if portfolio is None or not portfolio.holdings:
        st.error(t("common.no_holdings", name=portfolio_name))
        st.stop()

    # Soft fallback: shares-based view if every holding has shares + buy_date,
    # otherwise legacy weight-based view (with a warning).
    has_positions = portfolio.has_positions()

    if has_positions:
        # Compute per-holding P&L first; current values drive the derived weights.
        with st.spinner(t("analysis.building_series", name=portfolio_name)):
            pnl_rows, current_values = _holdings_pnl(portfolio.holdings, end)
            try:
                weights_norm = portfolio.weights_from_values(current_values)
            except ValueError:
                weights_norm = portfolio.normalized_weights()
            value_df = _build_portfolio_value_series(portfolio.holdings, start, end)
            rebased_df = _build_portfolio_series(weights_norm, start, end)
        if value_df.empty or rebased_df.empty:
            st.error(t("analysis.no_overlap"))
            st.stop()
    else:
        st.warning(t("portfolios.legacy_warning"))
        weights_norm = portfolio.normalized_weights()
        with st.spinner(t("analysis.building_series", name=portfolio_name)):
            rebased_df = _build_portfolio_series(weights_norm, start, end)
        if rebased_df.empty:
            st.error(t("analysis.no_overlap"))
            st.stop()
        value_df = pd.DataFrame()
        pnl_rows = []
        current_values = {}

    # Default chart: real value when available, rebased otherwise.
    _curve_options = ["value", "rebased"] if has_positions else ["rebased"]
    _curve_mode = st.radio(
        t("analysis.curve_mode"),
        _curve_options,
        index=0,
        horizontal=True,
        format_func=lambda c: t(f"analysis.curve_{c}"),
        key="analysis_curve_mode",
    ) if len(_curve_options) > 1 else "rebased"
    df = value_df if _curve_mode == "value" and has_positions else rebased_df

    if has_positions and _curve_mode == "value":
        st.title(t("analysis.title_portfolio_real", name=portfolio_name))
    else:
        st.title(t("analysis.title_portfolio", name=portfolio_name))

    st.caption(
        t("analysis.caption_portfolio")
        + ", ".join(f"{tk}: {w:.1%}" for tk, w in weights_norm.items())
    )

    # Holdings P&L table — only when we have shares-based holdings.
    if has_positions and pnl_rows:
        total_cost = sum(r["cost_basis"] or 0.0 for r in pnl_rows)
        total_value = sum(r["current_value"] or 0.0 for r in pnl_rows)
        total_pnl = total_value - total_cost
        total_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

        with st.container(border=True):
            st.subheader(t("holdings.title"))
            tc, tv, tp = st.columns(3)
            tc.metric(t("holdings.total_cost"),  f"{total_cost:,.2f}")
            tv.metric(t("holdings.total_value"), f"{total_value:,.2f}")
            tp.metric(t("holdings.total_pnl"),
                      f"{total_pnl:+,.2f}",
                      delta=f"{total_pct:+.2f}%")

            display_rows = []
            for r in pnl_rows:
                w_pct = (r["current_value"] / total_value * 100) if (r["current_value"] and total_value > 0) else None
                display_rows.append({
                    t("holdings.col_ticker"):        r["ticker"],
                    t("holdings.col_shares"):        r["shares"],
                    t("holdings.col_buy_date"):      r["buy_date"],
                    t("holdings.col_buy_price"):     r["buy_price"],
                    t("holdings.col_current_price"): r["current_price"],
                    t("holdings.col_cost"):          r["cost_basis"],
                    t("holdings.col_value"):         r["current_value"],
                    t("holdings.col_pnl"):           r["pnl"],
                    t("holdings.col_pnl_pct"):       r["pnl_pct"],
                    t("holdings.col_weight"):        w_pct,
                })
            st.dataframe(pd.DataFrame(display_rows), width="stretch", hide_index=True)

else:
    if not ticker:
        st.info(t("common.pick_ticker"))
        st.stop()
    with st.spinner(t("common.loading", name=ticker)):
        df = get_prices(ticker, start, end)
    if df.empty:
        st.error(t("common.no_data_range", ticker=ticker))
        st.stop()

    # Auto-save a freshly-typed custom ticker under its REAL category (detected
    # via yfinance's quoteType), not whatever Type the user had selected. Guarded
    # so the DB write only happens once per session per ticker.
    if choice == OTHER and ticker:
        _saved_marker = f"_saved_custom::{CURRENT_USER}::{ticker}"
        if _saved_marker not in st.session_state:
            try:
                _real_cat = _detect_category_cached(ticker)
                add_ticker(CURRENT_USER, _real_cat, ticker, name="")
                st.session_state[_saved_marker] = True
            except Exception:
                pass  # silent — UX nicety, not critical

    _currency = _currency_for(ticker)
    _name = lookup_name(CURRENT_USER, category, ticker)
    _title = t("analysis.title_ticker", ticker=ticker)
    if _name:
        _title += f" - {_name}"
    if _currency:
        _title += f" in {_currency}"
    st.title(_title)

# ── Past performance: separate price load over a longer window ──────────────
# We load up to 10y of history (PERF_PERIODS[-1] = 120 months) regardless of
# the user's chart lookback, so the perf grid can show 10y returns even when
# the chart only shows 1y. The +30-day buffer guards against weekends/holidays
# at the edge of each period boundary.
PERF_PERIODS = [("6m", 6), ("1y", 12), ("2y", 24), ("5y", 60), ("10y", 120)]
_perf_start = (
    pd.Timestamp(end) - pd.DateOffset(months=PERF_PERIODS[-1][1])
).date() - timedelta(days=30)
with st.spinner(t("analysis.loading_perf")):
    if is_portfolio:
        perf_prices = _build_portfolio_series(weights_norm, _perf_start, end)
    else:
        perf_prices = get_prices(ticker, _perf_start, end)


def _colored(value: str, ret: float | None) -> str:
    """Wrap a value in Streamlit's native color markdown based on sign."""
    if ret is None or ret == 0:
        return value
    return f":green[{value}]" if ret > 0 else f":red[{value}]"


def _compact_metric(
    col,
    label: str,
    tr_value: str,
    pr_value: str,
    tr_ret: float | None = None,
    pr_ret: float | None = None,
) -> None:
    col.caption(label)
    col.markdown(
        f"TR {_colored(tr_value, tr_ret)}  \nPR {_colored(pr_value, pr_ret)}"
    )


def _render_perf_grid(items: list[tuple], cols_per_row: int | None = None) -> None:
    """Render (label, tr_str, pr_str, tr_ret, pr_ret) tuples as a single-row grid.

    cols_per_row defaults to len(items) so all cells fit side-by-side on desktop;
    Streamlit auto-stacks them vertically on narrow viewports (phones)."""
    n = cols_per_row or max(len(items), 1)
    for i in range(0, len(items), n):
        chunk = items[i : i + n]
        cols = st.columns(n)
        for col, args in zip(cols, chunk):
            _compact_metric(col, *args)


st.subheader(t("analysis.past_perf"))
st.caption(t("analysis.past_perf_caption"))
if perf_prices.empty or len(perf_prices) < 2:
    st.caption(t("analysis.no_history"))
else:
    current_pr = float(perf_prices["close"].iloc[-1])
    current_tr = float(perf_prices["adj_close"].iloc[-1])

    period_items: list[tuple] = []
    for period_label, months in PERF_PERIODS:
        target = pd.Timestamp(end) - pd.DateOffset(months=months)
        before = perf_prices.loc[:target]
        if before.empty:
            period_items.append((period_label, "—", "—", None, None))
            continue
        past_pr = float(before["close"].iloc[-1])
        past_tr = float(before["adj_close"].iloc[-1])
        if past_pr <= 0 or past_tr <= 0:
            period_items.append((period_label, "—", "—", None, None))
            continue
        pr_ret = (current_pr / past_pr - 1) * 100
        tr_ret = (current_tr / past_tr - 1) * 100
        period_items.append(
            (period_label, f"{tr_ret:+.2f}%", f"{pr_ret:+.2f}%", tr_ret, pr_ret)
        )
    _render_perf_grid(period_items)

    year_items: list[tuple] = []
    for y in [end.year - i for i in range(5)]:
        start_ts = pd.Timestamp(year=y - 1, month=12, day=31)
        end_ts = (
            pd.Timestamp(year=y, month=12, day=31)
            if y < end.year
            else pd.Timestamp(end)
        )
        before_start = perf_prices.loc[:start_ts]
        before_end = perf_prices.loc[:end_ts]
        year_label = t("analysis.ytd", year=y) if y == end.year else str(y)
        if before_start.empty or before_end.empty:
            year_items.append((year_label, "—", "—", None, None))
            continue
        s_pr = float(before_start["close"].iloc[-1])
        e_pr = float(before_end["close"].iloc[-1])
        s_tr = float(before_start["adj_close"].iloc[-1])
        e_tr = float(before_end["adj_close"].iloc[-1])
        if s_pr <= 0 or s_tr <= 0:
            year_items.append((year_label, "—", "—", None, None))
            continue
        pr_ret = (e_pr / s_pr - 1) * 100
        tr_ret = (e_tr / s_tr - 1) * 100
        year_items.append(
            (year_label, f"{tr_ret:+.2f}%", f"{pr_ret:+.2f}%", tr_ret, pr_ret)
        )
    _render_perf_grid(year_items)

if is_portfolio and not perf_prices.empty and len(perf_prices) >= 2:
    render_llm_block(
        f"analysis_validate_{portfolio_name}",
        button_label=t("analysis.validate_btn"),
        clear_label=t("analysis.clear_validation"),
        prompt_fn=lambda: build_validate_portfolio_prompt(
            name=portfolio_name,
            holdings=portfolio.holdings,
            weights=weights_norm,
        ),
    )

elif not is_portfolio and not perf_prices.empty and len(perf_prices) >= 2:
    render_llm_block(
        f"analysis_describe_{ticker}",
        button_label=t("analysis.describe_btn"),
        clear_label=t("analysis.clear_snapshot"),
        prompt_fn=lambda: build_describe_ticker_prompt(
            ticker=ticker,
            name=_name,
            perf_prices=perf_prices,
            currency=_currency,
            end=end,
        ),
    )

# ── Chart: dynamic subplot grid ─────────────────────────────────────────────
# Rows are added in a fixed order so `_next_row` arithmetic stays predictable:
#     row 1: price (always)
#     row 2: volume (single-ticker only — portfolios have no volume)
#     row 3+: RSI panel, volatility panel — appended in that order if enabled
# `row_heights` is renormalized so the totals always sum to 1.0.
price_label = t("analysis.portfolio_value") if is_portfolio else t("analysis.price")
vol_title = t("analysis.volatility")
rsi_title = f"RSI {rsi_window}"

# Build the subplot grid: price, [volume,] [rsi,] [volatility].
if is_portfolio:
    row_heights = [1.0]
    subplot_titles = [price_label]
else:
    row_heights = [0.8, 0.2]
    subplot_titles = [price_label, t("analysis.volume")]
if show_rsi:
    row_heights.append(0.2)
    subplot_titles.append(rsi_title)
if show_volatility:
    row_heights.append(0.2)
    subplot_titles.append(vol_title)

# Renormalize row heights so everything fits to 1.0.
_total = sum(row_heights)
row_heights = [h / _total for h in row_heights]
rows = len(row_heights)

fig = make_subplots(
    rows=rows,
    cols=1,
    shared_xaxes=True,
    row_heights=row_heights,
    vertical_spacing=0.03,
    subplot_titles=subplot_titles,
)

chart_name = portfolio_name if is_portfolio else ticker
if is_portfolio:
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["close"],
            mode="lines",
            name=chart_name,
            line=dict(width=2),
        ),
        row=1,
        col=1,
    )
else:
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=chart_name,
        ),
        row=1,
        col=1,
    )

if show_smas:
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=sma(df["close"], int(sma_fast_window)),
            name=f"SMA {sma_fast_window}",
            line=dict(color="#1f77b4", width=1.5),
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=sma(df["close"], int(sma_slow_window)),
            name=f"SMA {sma_slow_window}",
            line=dict(color="#ff7f0e", width=1.5),
        ),
        row=1, col=1,
    )

if not is_portfolio:
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name=t("analysis.volume")), row=2, col=1)

_next_row = 2 if is_portfolio else 3  # row 1 = price, row 2 = volume (single-ticker only)

if show_rsi:
    _rsi_series = rsi(df["close"], int(rsi_window))
    fig.add_trace(
        go.Scatter(x=df.index, y=_rsi_series, name=rsi_title, line=dict(color="#2ca02c")),
        row=_next_row, col=1,
    )
    fig.add_hline(y=30, line_dash="dash", line_color="gray", row=_next_row, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="gray", row=_next_row, col=1)
    _next_row += 1

if show_volatility:
    _vol_series = (
        df["close"].pct_change()
        .rolling(int(vol_window))
        .std()
        * (252 ** 0.5)
        * 100
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=_vol_series, name=vol_title, line=dict(color="#9467bd")),
        row=_next_row,
        col=1,
    )

_chart_height = 800 + (120 if show_volatility else 0) + (120 if show_rsi else 0)
fig.update_layout(height=_chart_height, xaxis_rangeslider_visible=False, showlegend=show_legend)
st.plotly_chart(fig, width="stretch")

with st.expander(t("analysis.raw_data")):
    st.dataframe(df.tail(100))
