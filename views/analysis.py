from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pytalk import (
    get_prices,
    run_backtest,
    run_portfolio_backtest,
    run_portfolio_buy_hold,
)
from pytalk.custom_tickers import (
    add_ticker,
    combined_label,
    combined_symbols,
    lookup_name,
)
from pytalk.data import detect_category, get_currency
from pytalk.indicators import rsi
from pytalk.llm import ask_llm_stream, llm_available, unavailable_message
from pytalk.portfolios import get_portfolio, list_portfolios
from pytalk.strategies import STRATEGIES
from pytalk.strategies.display import indicators_for
from pytalk.strategies.signals import signals_for
from pytalk.universe import CATEGORIES, OTHER, UNIVERSE, label, tickers

CURRENT_USER = (st.user.email or st.user.get("preferred_username", "")).strip().lower()

# Preserve widget state across page navigation.
# Skip keys that look like button widgets — Streamlit forbids re-assigning their state.
_BUTTON_HINTS = ("_rm_", "_back_", "_add", "_save", "_del_", "_explain", "save_", "del_", "clear_", "FormSubmitter")
for _k in list(st.session_state.keys()):
    if any(_h in _k for _h in _BUTTON_HINTS):
        continue
    try:
        st.session_state[_k] = st.session_state[_k]
    except Exception:
        pass


def _pop_ss(key: str) -> None:
    """Callback helper — drops a session_state key before Streamlit's auto-rerun."""
    st.session_state.pop(key, None)

with st.sidebar:
    source = st.radio(
        "Source",
        ["Single ticker", "Portfolio"],
        horizontal=True,
        key="analysis_source",
    )

    ticker: str | None = None
    category: str | None = None
    portfolio_name: str | None = None

    if source == "Single ticker":
        category = st.selectbox(
            "Type",
            CATEGORIES,
            index=CATEGORIES.index("ETF"),
            key="analysis_category",
        )
        _symbols = combined_symbols(CURRENT_USER, category)
        options = _symbols + [OTHER]
        _default_ticker = (
            "CASH.TO" if category == "ETF" and "CASH.TO" in _symbols else _symbols[0]
        )
        _default_idx = _symbols.index(_default_ticker) if _default_ticker in _symbols else 0
        choice = st.selectbox(
            "Ticker",
            options,
            index=_default_idx,
            format_func=lambda s: combined_label(CURRENT_USER, category, s),
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
    else:
        portfolio_names = list_portfolios(CURRENT_USER)
        if not portfolio_names:
            st.warning("No portfolios yet. Create one on the Portfolios page.")
        else:
            portfolio_name = st.selectbox(
                "Portfolio", portfolio_names, key="analysis_portfolio"
            )

    lookback_days = st.slider(
        "Lookback (days)", 30, 1825, 365, key="analysis_lookback"
    )
    end = st.date_input("End date", value=date.today(), key="analysis_end")
    start = end - timedelta(days=lookback_days)
    strategy_name = st.selectbox(
        "Strategy",
        list(STRATEGIES.keys()),
        key="analysis_strategy",
    )
    show_indicators = st.checkbox(
        "Show indicators", value=True, key="analysis_show_indicators"
    )

    st.divider()
    cash = st.number_input(
        "Starting cash",
        min_value=1_000,
        value=10_000,
        step=1_000,
        key="analysis_cash",
    )
    commission_bps = st.number_input(
        "Commission (bps per trade)", 0, 100, 20, key="analysis_commission"
    )
    rebalance_freq = "none"
    if source == "Portfolio" and strategy_name == "Buy & Hold":
        _reb_label = st.selectbox(
            "Rebalance frequency",
            ["None (drift)", "Monthly", "Quarterly", "Yearly"],
            index=2,
            key="analysis_reb_freq",
        )
        rebalance_freq = {
            "None (drift)": "none",
            "Monthly": "M",
            "Quarterly": "Q",
            "Yearly": "Y",
        }[_reb_label]
    run_bt = st.button("🧪 Run backtest", type="primary")

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


if is_portfolio:
    if not portfolio_name:
        st.info("Pick a portfolio to begin.")
        st.stop()
    portfolio = get_portfolio(CURRENT_USER, portfolio_name)
    if portfolio is None or not portfolio.holdings:
        st.error(f"Portfolio “{portfolio_name}” has no holdings.")
        st.stop()
    weights_norm = portfolio.normalized_weights()
    with st.spinner(f"Building “{portfolio_name}” series…"):
        df = _build_portfolio_series(weights_norm, start, end)
    if df.empty:
        st.error("No overlapping price data across the portfolio's holdings.")
        st.stop()
    _title = f"Technical analysis for portfolio “{portfolio_name}”"
    st.title(_title)
    st.caption(
        "Weighted buy-and-hold equity curve (rebased to 100 at range start). "
        + ", ".join(f"{t}: {w:.1%}" for t, w in weights_norm.items())
    )

else:
    if not ticker:
        st.info("Pick a ticker to begin.")
        st.stop()
    with st.spinner(f"Loading {ticker}…"):
        df = get_prices(ticker, start, end)
    if df.empty:
        st.error(f"No data for {ticker} in the selected range.")
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
    _title = f"Technical analysis for {ticker}"
    if _name:
        _title += f" - {_name}"
    if _currency:
        _title += f" in {_currency}"
    st.title(_title)

PERF_PERIODS = [("6m", 6), ("1y", 12), ("2y", 24), ("5y", 60), ("10y", 120)]
_perf_start = (
    pd.Timestamp(end) - pd.DateOffset(months=PERF_PERIODS[-1][1])
).date() - timedelta(days=30)
with st.spinner("Loading past performance…"):
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


st.subheader("Past performance")
st.caption(
    "**TR** = Total Return (price + reinvested dividends, retirement-relevant). "
    "**PR** = Price Return (split-adjusted, no dividends — matches Yahoo/Google)."
)
if perf_prices.empty or len(perf_prices) < 2:
    st.caption("No historical data available.")
else:
    current_pr = float(perf_prices["close"].iloc[-1])
    current_tr = float(perf_prices["adj_close"].iloc[-1])

    cols = st.columns(len(PERF_PERIODS))
    for (period_label, months), col in zip(PERF_PERIODS, cols):
        target = pd.Timestamp(end) - pd.DateOffset(months=months)
        before = perf_prices.loc[:target]
        if before.empty:
            _compact_metric(col, period_label, "—", "—")
            continue
        past_pr = float(before["close"].iloc[-1])
        past_tr = float(before["adj_close"].iloc[-1])
        if past_pr <= 0 or past_tr <= 0:
            _compact_metric(col, period_label, "—", "—")
            continue
        pr_ret = (current_pr / past_pr - 1) * 100
        tr_ret = (current_tr / past_tr - 1) * 100
        _compact_metric(
            col,
            period_label,
            f"{tr_ret:+.2f}%",
            f"{pr_ret:+.2f}%",
            tr_ret=tr_ret,
            pr_ret=pr_ret,
        )

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
            _compact_metric(year_cols[i], year_label, "—", "—")
            continue
        s_pr = float(before_start["close"].iloc[-1])
        e_pr = float(before_end["close"].iloc[-1])
        s_tr = float(before_start["adj_close"].iloc[-1])
        e_tr = float(before_end["adj_close"].iloc[-1])
        if s_pr <= 0 or s_tr <= 0:
            _compact_metric(year_cols[i], year_label, "—", "—")
            continue
        pr_ret = (e_pr / s_pr - 1) * 100
        tr_ret = (e_tr / s_tr - 1) * 100
        _compact_metric(
            year_cols[i],
            year_label,
            f"{tr_ret:+.2f}%",
            f"{pr_ret:+.2f}%",
            tr_ret=tr_ret,
            pr_ret=pr_ret,
        )

if is_portfolio and not perf_prices.empty and len(perf_prices) >= 2:
    _validate_key = f"_analysis_validate_{portfolio_name}"
    if st.button("🧠 Validate portfolio"):
        if not llm_available():
            st.error(unavailable_message())
        else:
            _by_type: dict[str, float] = {}
            for _h in portfolio.holdings:
                _by_type[_h.category] = (
                    _by_type.get(_h.category, 0.0) + weights_norm[_h.ticker]
                )
            _mix_text = ", ".join(f"{t}: {w:.1%}" for t, w in _by_type.items())
            _holdings_text = "\n".join(
                f"  - {_h.ticker} ({_h.category}) "
                f"[{UNIVERSE.get(_h.category, {}).get(_h.ticker) or 'custom'}] — "
                f"{weights_norm[_h.ticker]:.1%}"
                for _h in portfolio.holdings
            )
            _prompt = f"""Review this portfolio structure.

Name: {portfolio_name}
Total holdings: {len(portfolio.holdings)}
Asset-type mix: {_mix_text}

Holdings:
{_holdings_text}

Respond as a markdown numbered list — one short sentence per point, no introduction, no final paragraph:
1. Overall diversification — across asset classes, geography, and sectors.
2. Concentration risks — any single holding or type too dominant?
3. Overlap — do multiple holdings track the same thing (e.g. two S&P 500 ETFs)?
4. What kind of investor this portfolio suits (growth / income / capital preservation).
5. One honest caveat (hidden correlations, home-bias, missing asset classes, etc.).
6. One constructive observation — what would make it more robust, without recommending specific tickers.

Don't invent facts about any holding you don't recognise; just say "unfamiliar".
"""
            with st.container(border=True):
                _full_val = st.write_stream(ask_llm_stream(_prompt))
            st.session_state[_validate_key] = _full_val
    else:
        _stored_validate = st.session_state.get(_validate_key)
        if _stored_validate:
            with st.container(border=True):
                st.markdown(_stored_validate)

    if st.session_state.get(_validate_key):
        st.button(
            "Clear validation",
            key=f"clear_analysis_validate_{portfolio_name}",
            on_click=_pop_ss,
            args=(_validate_key,),
        )

elif not is_portfolio and not perf_prices.empty and len(perf_prices) >= 2:
    _describe_key = f"_analysis_describe_{ticker}"
    if st.button("🧠 Describe current state"):
        if not llm_available():
            st.error(unavailable_message())
        else:
            _close = perf_prices["close"]
            _adj = perf_prices["adj_close"]
            _curr = float(_close.iloc[-1])

            def _last(s: pd.Series) -> float | None:
                v = s.dropna()
                return float(v.iloc[-1]) if not v.empty else None

            _sma20 = _last(_close.rolling(20).mean())
            _sma50 = _last(_close.rolling(50).mean())
            _sma200 = _last(_close.rolling(200).mean())
            _rsi14 = _last(rsi(_close, 14))

            _year_close = _close.loc[pd.Timestamp(end) - pd.DateOffset(months=12) :]
            _pos_52w: float | None = None
            _vol: float | None = None
            if not _year_close.empty and _year_close.max() > _year_close.min():
                _pos_52w = (
                    (_curr - float(_year_close.min()))
                    / (float(_year_close.max()) - float(_year_close.min()))
                    * 100
                )
            _year_rets = _year_close.pct_change().dropna()
            if len(_year_rets) > 20:
                _vol = float(_year_rets.std()) * (252 ** 0.5) * 100

            # 1y TR vs PR → implied dividend yield
            _target_1y = pd.Timestamp(end) - pd.DateOffset(months=12)
            _before_1y = perf_prices.loc[:_target_1y]
            _div_text = "n/a"
            if not _before_1y.empty:
                _past_pr = float(_before_1y["close"].iloc[-1])
                _past_tr = float(_before_1y["adj_close"].iloc[-1])
                if _past_pr > 0 and _past_tr > 0:
                    _pr_1y = (_curr / _past_pr - 1) * 100
                    _tr_1y = (float(_adj.iloc[-1]) / _past_tr - 1) * 100
                    _gap = _tr_1y - _pr_1y
                    if _gap > 0.5:
                        _div_text = f"~{_gap:.1f}% (meaningful dividend contribution)"
                    elif _gap > 0.05:
                        _div_text = f"~{_gap:.2f}% (small dividend)"
                    else:
                        _div_text = "negligible / no dividend"

            def _fmt(v: float | None, suffix: str = "") -> str:
                return "—" if v is None else f"{v:.2f}{suffix}"

            _name_bit = UNIVERSE.get(category, {}).get(ticker, "")
            _prompt = f"""Summarize the current technical state of {ticker}{' (' + _name_bit + ')' if _name_bit else ''}.

Current price: {_curr:.2f} {_currency or ''}
Moving averages:
  SMA 20:  {_fmt(_sma20)}
  SMA 50:  {_fmt(_sma50)}
  SMA 200: {_fmt(_sma200)}
Momentum:
  RSI(14): {_fmt(_rsi14)}
Range:
  52-week position: {_fmt(_pos_52w, '%')} (0 = at 52w low, 100 = at 52w high)
Risk:
  Annualized volatility (1y): {_fmt(_vol, '%')}
Dividend character:
  1y TR-PR gap: {_div_text}

Respond as a markdown numbered list - one short sentence per point, no introduction, no final paragraph:
1. Trend — where the price sits vs SMA 50 and SMA 200, what that suggests.
2. Momentum — what RSI(14) and recent moves imply (overbought / neutral / oversold).
3. Volatility regime — calm, elevated, or extreme compared to normal equity (~15-20%).
4. Range position — near 52-week high, middle, or near 52-week low.
5. Dividend character — is this a meaningful income payer?
6. Honest caveat — what this snapshot does NOT tell you (company fundamentals, earnings, macro, valuation, current news).
"""
            with st.container(border=True):
                _full_desc = st.write_stream(ask_llm_stream(_prompt))
            st.session_state[_describe_key] = _full_desc
    else:
        _stored_desc = st.session_state.get(_describe_key)
        if _stored_desc:
            with st.container(border=True):
                st.markdown(_stored_desc)

    if st.session_state.get(_describe_key):
        st.button(
            "Clear snapshot",
            key=f"clear_analysis_describe_{ticker}",
            on_click=_pop_ss,
            args=(_describe_key,),
        )

indicators = indicators_for(strategy_name, df) if show_indicators else []
price_overlays = [ind for ind in indicators if ind.panel == "price"]
sub_indicators = [ind for ind in indicators if ind.panel == "sub"]

metrics = [("Close", f"{df['close'].iloc[-1]:.2f}")]
for ind in indicators[:3]:
    value = ind.series.dropna()
    metrics.append((ind.name, f"{value.iloc[-1]:.2f}" if not value.empty else "—"))
with st.container(border=True):
    _mcols = st.columns(len(metrics))
    for _mcol, (_mname, _mvalue) in zip(_mcols, metrics):
        _mcol.caption(_mname)
        _mcol.markdown(f"**{_mvalue}**")

has_sub = bool(sub_indicators)
price_label = "Portfolio value" if is_portfolio else "Price"

if is_portfolio:
    rows = 2 if has_sub else 1
    row_heights = [0.75, 0.25] if has_sub else [1.0]
    subplot_titles = [price_label] + ([strategy_name] if has_sub else [])
else:
    rows = 3 if has_sub else 2
    row_heights = [0.65, 0.2, 0.15] if has_sub else [0.8, 0.2]
    subplot_titles = [price_label, "Volume"] + ([strategy_name] if has_sub else [])

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

if not is_portfolio:
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume"), row=2, col=1)

if has_sub:
    sub_row = 2 if is_portfolio else 3
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
st.plotly_chart(fig, width="stretch")

# ── Backtest run + results ──────────────────────────────────────────────────
strategy_class = STRATEGIES[strategy_name]
commission_frac = commission_bps / 10_000

if run_bt:
    if is_portfolio:
        with st.spinner("Running portfolio backtest…"):
            prices_by_ticker: dict[str, pd.DataFrame] = {}
            weights_raw: dict[str, float] = {}
            for h in portfolio.holdings:
                prices_by_ticker[h.ticker] = get_prices(h.ticker, start, end)
                weights_raw[h.ticker] = h.weight
            try:
                if strategy_name == "Buy & Hold":
                    bt_result = run_portfolio_buy_hold(
                        prices_by_ticker,
                        weights_raw,
                        cash=float(cash),
                        commission=commission_frac,
                        rebalance_freq=rebalance_freq,
                    )
                else:
                    bt_result = run_portfolio_backtest(
                        prices_by_ticker,
                        weights_raw,
                        strategy_class,
                        cash=float(cash),
                        commission=commission_frac,
                    )
                st.session_state["_analysis_bt"] = {
                    "mode": "Portfolio",
                    "strategy_name": strategy_name,
                    "portfolio_name": portfolio_name,
                    "rebalance_freq": rebalance_freq,
                    "result": bt_result,
                }
            except ValueError as e:
                st.error(str(e))
    else:
        with st.spinner(f"Running backtest on {ticker}…"):
            try:
                bt_result = run_backtest(
                    df, strategy_class, cash=float(cash), commission=commission_frac
                )
                st.session_state["_analysis_bt"] = {
                    "mode": "Single ticker",
                    "strategy_name": strategy_name,
                    "ticker": ticker,
                    "category": category,
                    "result": bt_result,
                }
            except Exception as e:
                st.error(f"Backtest failed: {e}")

_snap = st.session_state.get("_analysis_bt")
if _snap is not None:
    _show = (
        _snap.get("mode") == "Portfolio"
        and _snap.get("portfolio_name") == portfolio_name
        if is_portfolio
        else _snap.get("mode") == "Single ticker"
        and _snap.get("ticker") == ticker
    )
    if _show:
        st.divider()
        _bt_strategy = _snap["strategy_name"]
        if _snap["mode"] == "Single ticker":
            st.subheader(f"Backtest — {_snap['ticker']} with {_bt_strategy}")
            _res = _snap["result"]
            _stats = _res.stats
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Return", f"{_stats['Return [%]']:.2f}%")
            c2.metric("Buy & Hold", f"{_stats['Buy & Hold Return [%]']:.2f}%")
            c3.metric("Sharpe", f"{_stats['Sharpe Ratio']:.2f}")
            c4.metric("Max Drawdown", f"{_stats['Max. Drawdown [%]']:.2f}%")

            _eq = _res.equity_curve
            _fig = go.Figure()
            _fig.add_trace(go.Scatter(x=_eq.index, y=_eq["Equity"], name="Equity"))
            _fig.add_trace(
                go.Scatter(
                    x=_eq.index,
                    y=_eq["DrawdownPct"] * 100,
                    name="Drawdown %",
                    yaxis="y2",
                )
            )
            _fig.update_layout(
                height=400,
                yaxis=dict(title="Equity"),
                yaxis2=dict(title="Drawdown %", overlaying="y", side="right"),
            )
            st.plotly_chart(_fig, width="stretch")

            with st.expander("Trades"):
                st.dataframe(_res.trades)
            with st.expander("Full stats"):
                st.dataframe(_stats.astype(str).to_frame("value"))

            if st.button("🧠 Explain this result"):
                if not llm_available():
                    st.error(unavailable_message())
                else:
                    _prompt = f"""Explain this backtest result for a retail investor.

Strategy: {_bt_strategy}
Ticker: {_snap['ticker']} ({_snap.get('category', '')})
Return: {_stats['Return [%]']:.2f}%
Buy & Hold return: {_stats['Buy & Hold Return [%]']:.2f}%
Sharpe Ratio: {_stats['Sharpe Ratio']:.2f}
Max Drawdown: {_stats['Max. Drawdown [%]']:.2f}%
Number of trades: {int(_stats.get('# Trades', 0))}
Win rate: {float(_stats.get('Win Rate [%]', 0)):.1f}%

Respond as a markdown numbered list — one short sentence per point, no introduction, no final paragraph:
1. Did the strategy beat buy-and-hold? By how much?
2. Was the risk-adjusted return (Sharpe) reasonable?
3. Was the drawdown psychologically tradeable?
4. One honest caveat (overfitting, small sample, single-asset, etc.)
"""
                    with st.container(border=True):
                        _full_explain = st.write_stream(ask_llm_stream(_prompt))
                    st.session_state["_analysis_explain"] = _full_explain
            else:
                _stored_explain = st.session_state.get("_analysis_explain")
                if _stored_explain:
                    with st.container(border=True):
                        st.markdown(_stored_explain)

            if st.session_state.get("_analysis_explain"):
                st.button(
                    "Clear explanation",
                    key="clear_analysis_explain_single",
                    on_click=_pop_ss,
                    args=("_analysis_explain",),
                )

        else:  # Portfolio
            _title_suffix = _bt_strategy
            if _bt_strategy == "Buy & Hold" and _snap.get("rebalance_freq") != "none":
                _title_suffix += f" (rebalance: {_snap['rebalance_freq']})"
            st.subheader(
                f"Backtest — portfolio “{_snap['portfolio_name']}” with {_title_suffix}"
            )
            _res = _snap["result"]
            if _res.skipped:
                st.warning(
                    "Skipped (no data or failed backtest): " + ", ".join(_res.skipped)
                )
            _stats = _res.stats
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Return", f"{_stats['Return [%]']:.2f}%")
            c2.metric("Sharpe", f"{_stats['Sharpe Ratio']:.2f}")
            c3.metric("Max Drawdown", f"{_stats['Max. Drawdown [%]']:.2f}%")
            c4.metric("Final Equity", f"{_stats['Final Equity']:,.0f}")

            _eq = _res.equity
            _roll_max = _eq.cummax()
            _dd = ((_eq / _roll_max) - 1) * 100
            _fig = go.Figure()
            _fig.add_trace(go.Scatter(x=_eq.index, y=_eq.values, name="Equity"))
            _fig.add_trace(
                go.Scatter(x=_eq.index, y=_dd.values, name="Drawdown %", yaxis="y2")
            )
            _fig.update_layout(
                height=400,
                yaxis=dict(title="Equity"),
                yaxis2=dict(title="Drawdown %", overlaying="y", side="right"),
            )
            st.plotly_chart(_fig, width="stretch")

            if _res.per_ticker:
                per_rows = []
                for tkr, per_result in _res.per_ticker.items():
                    s = per_result.stats
                    per_rows.append(
                        {
                            "Ticker": tkr,
                            "Weight": f"{_res.weights.get(tkr, 0):.1%}",
                            "Return [%]": round(float(s["Return [%]"]), 2),
                            "Buy & Hold [%]": round(
                                float(s["Buy & Hold Return [%]"]), 2
                            ),
                            "Sharpe": round(float(s["Sharpe Ratio"]), 2),
                            "Max DD [%]": round(float(s["Max. Drawdown [%]"]), 2),
                            "# Trades": int(s.get("# Trades", 0)),
                        }
                    )
                with st.expander("Per-ticker results"):
                    st.dataframe(pd.DataFrame(per_rows), width="stretch")

            if st.button("🧠 Explain this result"):
                if not llm_available():
                    st.error(unavailable_message())
                else:
                    per_ticker_text = "\n".join(
                        f"  {r['Ticker']} (weight {r['Weight']}): "
                        f"return {r['Return [%]']}%, B&H {r['Buy & Hold [%]']}%, "
                        f"Sharpe {r['Sharpe']}, DD {r['Max DD [%]']}%"
                        for r in (per_rows if _res.per_ticker else [])
                    )
                    _prompt = f"""Explain this portfolio backtest for a retail investor.

Portfolio: {_snap['portfolio_name']}
Strategy: {_bt_strategy}
Rebalance: {_snap.get('rebalance_freq', 'n/a')}
Aggregate return: {_stats['Return [%]']:.2f}%
Aggregate Sharpe: {_stats['Sharpe Ratio']:.2f}
Aggregate Max Drawdown: {_stats['Max. Drawdown [%]']:.2f}%
Final equity: {_stats['Final Equity']:,.0f}

Per-ticker results:
{per_ticker_text}

Respond as a markdown numbered list — one short sentence per point, no introduction, no final paragraph:
1. Did the portfolio-level strategy produce a reasonable risk-adjusted return?
2. Which holdings carried the portfolio? Which ones hurt it?
3. Was the diversification helpful (lower drawdown than any single name)?
4. One honest caveat about applying the same strategy to very different assets.
"""
                    with st.container(border=True):
                        _full_explain = st.write_stream(ask_llm_stream(_prompt))
                    st.session_state["_analysis_explain"] = _full_explain
            else:
                _stored_explain = st.session_state.get("_analysis_explain")
                if _stored_explain:
                    with st.container(border=True):
                        st.markdown(_stored_explain)

            if st.session_state.get("_analysis_explain"):
                st.button(
                    "Clear explanation",
                    key="clear_analysis_explain_portfolio",
                    on_click=_pop_ss,
                    args=("_analysis_explain",),
                )

with st.expander("Raw data"):
    st.dataframe(df.tail(100))
