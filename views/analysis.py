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
from pytalk.i18n import category_label, t
from pytalk.indicators import rsi
from pytalk.llm import ask_llm_stream, llm_available, unavailable_message
from pytalk.portfolios import get_portfolio, list_portfolios
from pytalk.strategies import STRATEGIES
from pytalk.strategies.display import indicators_for
from pytalk.strategies.signals import signals_for
from pytalk.universe import CATEGORIES, OTHER, UNIVERSE, label, tickers

CURRENT_USER = (st.user.email or st.user.get("preferred_username", "")).strip().lower()

_SOURCE_LABELS = {
    "Single ticker": "common.source_single",
    "Portfolio": "common.source_portfolio",
}
_REB_LABELS = {
    "None (drift)": "common.reb_none",
    "Monthly": "common.reb_monthly",
    "Quarterly": "common.reb_quarterly",
    "Yearly": "common.reb_yearly",
}


def _pop_ss(key: str) -> None:
    """Callback helper — drops a session_state key before Streamlit's auto-rerun."""
    st.session_state.pop(key, None)

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
    strategy_name = st.selectbox(
        t("common.strategy"),
        list(STRATEGIES.keys()),
        key="analysis_strategy",
    )
    show_indicators = st.checkbox(
        t("common.show_indicators"), value=True, key="analysis_show_indicators"
    )
    show_volatility = st.checkbox(
        t("common.show_volatility"), value=False, key="analysis_show_volatility"
    )
    if show_volatility:
        vol_window = st.slider(
            t("common.vol_window"), 5, 252, 21, key="analysis_vol_window"
        )
    else:
        vol_window = 21

    # Strategy-specific tuning knobs. Each block only renders when its strategy
    # is selected, so the sidebar stays uncluttered.
    params: dict[str, float | int] = {}
    if strategy_name == "Buy & Hold":
        pass  # no params
    elif strategy_name == "Faber Trend Filter":
        params["window"] = st.slider(
            t("backtest.sma_window_faber"), 20, 500, 200, key="analysis_faber_window"
        )
    elif strategy_name == "SMA Cross":
        params["fast"] = st.slider(t("backtest.sma_fast"), 5, 100, 20, key="analysis_sma_fast")
        params["slow"] = st.slider(t("backtest.sma_slow"), 20, 300, 50, key="analysis_sma_slow")
    elif strategy_name == "MACD Cross":
        params["fast"] = st.slider(t("backtest.ema_fast"), 5, 50, 12, key="analysis_macd_fast")
        params["slow"] = st.slider(t("backtest.ema_slow"), 10, 100, 26, key="analysis_macd_slow")
        params["signal"] = st.slider(t("backtest.signal_ema"), 3, 30, 9, key="analysis_macd_signal")
    elif strategy_name == "RSI Mean Reversion":
        params["window"] = st.slider(t("backtest.rsi_window"), 2, 50, 14, key="analysis_rsi_window")
        params["oversold"] = st.slider(t("backtest.oversold"), 5, 45, 30, key="analysis_rsi_oversold")
        params["overbought"] = st.slider(
            t("backtest.overbought"), 55, 95, 70, key="analysis_rsi_overbought"
        )
    elif strategy_name == "Bollinger Mean Reversion":
        params["window"] = st.slider(t("backtest.window"), 5, 100, 20, key="analysis_boll_window")
        params["k"] = st.slider(
            t("backtest.stddev"), 1.0, 4.0, 2.0, step=0.1, key="analysis_boll_k"
        )
    elif strategy_name == "Donchian Breakout":
        params["entry_window"] = st.slider(
            t("backtest.donch_entry"), 5, 100, 20, key="analysis_donch_entry"
        )
        params["exit_window"] = st.slider(
            t("backtest.donch_exit"), 3, 60, 10, key="analysis_donch_exit"
        )
    elif strategy_name == "VWAP Reversion":
        params["window"] = st.slider(
            t("backtest.vwap_window"), 5, 100, 20, key="analysis_vwap_window"
        )
        params["k"] = st.slider(
            t("backtest.stddev_entry"), 0.5, 4.0, 1.5, step=0.1, key="analysis_vwap_k"
        )

    st.divider()
    cash = st.number_input(
        t("common.starting_cash"),
        min_value=1_000,
        value=10_000,
        step=1_000,
        key="analysis_cash",
    )
    commission_bps = st.number_input(
        t("common.commission_bps"), 0, 100, 20, key="analysis_commission"
    )
    rebalance_freq = "none"
    if source == "Portfolio" and strategy_name == "Buy & Hold":
        _reb_label = st.selectbox(
            t("common.rebalance_freq"),
            ["None (drift)", "Monthly", "Quarterly", "Yearly"],
            index=2,
            format_func=lambda s: t(_REB_LABELS[s]),
            key="analysis_reb_freq",
        )
        rebalance_freq = {
            "None (drift)": "none",
            "Monthly": "M",
            "Quarterly": "Q",
            "Yearly": "Y",
        }[_reb_label]
    weight_source = "manual"
    if source == "Portfolio":
        weight_source = st.radio(
            t("backtest.weight_source"),
            ["shares", "manual"],
            index=0,
            format_func=lambda s: t(
                "backtest.weight_from_shares" if s == "shares" else "backtest.weight_manual"
            ),
            key="analysis_weight_source",
        )
    run_bt = st.button(t("common.run_backtest"), type="primary")

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


st.subheader(t("analysis.past_perf"))
st.caption(t("analysis.past_perf_caption"))
if perf_prices.empty or len(perf_prices) < 2:
    st.caption(t("analysis.no_history"))
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
        year_label = t("analysis.ytd", year=y) if y == end.year else str(y)
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
    if st.button(t("analysis.validate_btn")):
        if not llm_available():
            st.error(unavailable_message())
        else:
            _by_type: dict[str, float] = {}
            for _h in portfolio.holdings:
                _by_type[_h.category] = (
                    _by_type.get(_h.category, 0.0) + weights_norm[_h.ticker]
                )
            _mix_text = ", ".join(f"{tk}: {w:.1%}" for tk, w in _by_type.items())
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
            t("analysis.clear_validation"),
            key=f"clear_analysis_validate_{portfolio_name}",
            on_click=_pop_ss,
            args=(_validate_key,),
        )

elif not is_portfolio and not perf_prices.empty and len(perf_prices) >= 2:
    _describe_key = f"_analysis_describe_{ticker}"
    if st.button(t("analysis.describe_btn")):
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
            t("analysis.clear_snapshot"),
            key=f"clear_analysis_describe_{ticker}",
            on_click=_pop_ss,
            args=(_describe_key,),
        )

indicators = indicators_for(strategy_name, df, **params) if show_indicators else []
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
price_label = t("analysis.portfolio_value") if is_portfolio else t("analysis.price")
vol_title = t("analysis.volatility")

# Build the subplot grid: price, [volume,] [strategy sub,] [volatility].
if is_portfolio:
    row_heights = [1.0]
    subplot_titles = [price_label]
else:
    row_heights = [0.8, 0.2]
    subplot_titles = [price_label, t("analysis.volume")]
if has_sub:
    row_heights.append(0.2)
    subplot_titles.append(strategy_name)
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

for ind in price_overlays:
    fig.add_trace(go.Scatter(x=df.index, y=ind.series, name=ind.name), row=1, col=1)

if show_indicators:
    signals = signals_for(strategy_name, df, **params)
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
                name=t("analysis.buy"),
                hovertemplate=t("analysis.buy") + "<br>%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
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
                name=t("analysis.sell"),
                hovertemplate=t("analysis.sell") + "<br>%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

if not is_portfolio:
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name=t("analysis.volume")), row=2, col=1)

_next_row = 2 if is_portfolio else 3  # row 1 = price, row 2 = volume (single-ticker only)
if has_sub:
    for ind in sub_indicators:
        fig.add_trace(go.Scatter(x=df.index, y=ind.series, name=ind.name), row=_next_row, col=1)
    seen_hlines: set[float] = set()
    for ind in sub_indicators:
        for h in ind.hlines:
            if h in seen_hlines:
                continue
            seen_hlines.add(h)
            fig.add_hline(y=h, line_dash="dash", line_color="gray", row=_next_row, col=1)
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

# Give the chart a bit more height when extra panels are on so the price panel
# doesn't get squeezed below readability.
_chart_height = 800 + (120 if has_sub else 0) + (120 if show_volatility else 0)
fig.update_layout(height=_chart_height, xaxis_rangeslider_visible=False, showlegend=True)
st.plotly_chart(fig, width="stretch")

# ── Backtest run + results ──────────────────────────────────────────────────
strategy_class = STRATEGIES[strategy_name]
commission_frac = commission_bps / 10_000

if run_bt:
    if is_portfolio:
        # Resolve weight source (with the same soft fallback as the standalone Backtest had).
        effective_source = weight_source
        if weight_source == "shares" and not portfolio.has_positions():
            st.warning(t("backtest.weight_fallback_warn"))
            effective_source = "manual"
        with st.spinner(t("analysis.running_portfolio")):
            prices_by_ticker: dict[str, pd.DataFrame] = {}
            weights_raw: dict[str, float] = {}
            for h in portfolio.holdings:
                prices_by_ticker[h.ticker] = get_prices(h.ticker, start, end)
            if effective_source == "shares":
                # Reference price = close on the analysis start date.
                for h in portfolio.holdings:
                    pdf = prices_by_ticker[h.ticker]
                    if pdf.empty:
                        weights_raw[h.ticker] = 0.0
                        continue
                    weights_raw[h.ticker] = float(h.shares) * float(pdf["close"].iloc[0])
            else:
                for h in portfolio.holdings:
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
                        **params,
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
        with st.spinner(t("analysis.running_ticker", ticker=ticker)):
            try:
                bt_result = run_backtest(
                    df, strategy_class, cash=float(cash), commission=commission_frac, **params
                )
                st.session_state["_analysis_bt"] = {
                    "mode": "Single ticker",
                    "strategy_name": strategy_name,
                    "ticker": ticker,
                    "category": category,
                    "result": bt_result,
                }
            except Exception as e:
                st.error(t("analysis.bt_failed", error=e))

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
            st.subheader(t("analysis.bt_title_ticker", ticker=_snap['ticker'], strategy=_bt_strategy))
            _res = _snap["result"]
            _stats = _res.stats
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("analysis.metric_return"), f"{_stats['Return [%]']:.2f}%")
            c2.metric(t("analysis.metric_bh"), f"{_stats['Buy & Hold Return [%]']:.2f}%")
            c3.metric(t("analysis.metric_sharpe"), f"{_stats['Sharpe Ratio']:.2f}")
            c4.metric(t("analysis.metric_mdd"), f"{_stats['Max. Drawdown [%]']:.2f}%")

            _eq = _res.equity_curve
            _fig = go.Figure()
            _fig.add_trace(go.Scatter(x=_eq.index, y=_eq["Equity"], name=t("analysis.equity_label")))
            _fig.add_trace(
                go.Scatter(
                    x=_eq.index,
                    y=_eq["DrawdownPct"] * 100,
                    name=t("analysis.drawdown_label"),
                    yaxis="y2",
                )
            )
            _fig.update_layout(
                height=400,
                yaxis=dict(title=t("analysis.equity_label")),
                yaxis2=dict(title=t("analysis.drawdown_label"), overlaying="y", side="right"),
            )
            st.plotly_chart(_fig, width="stretch")

            with st.expander(t("analysis.trades")):
                st.dataframe(_res.trades)
            with st.expander(t("analysis.full_stats")):
                st.dataframe(_stats.astype(str).to_frame("value"))

            if st.button(t("analysis.explain_btn")):
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
                    t("analysis.clear_explain"),
                    key="clear_analysis_explain_single",
                    on_click=_pop_ss,
                    args=("_analysis_explain",),
                )

        else:  # Portfolio
            _title_suffix = _bt_strategy
            if _bt_strategy == "Buy & Hold" and _snap.get("rebalance_freq") != "none":
                _title_suffix += f" (rebalance: {_snap['rebalance_freq']})"
            st.subheader(
                t("analysis.bt_title_portfolio", name=_snap['portfolio_name'], strategy=_title_suffix)
            )
            _res = _snap["result"]
            if _res.skipped:
                st.warning(t("analysis.skipped", list=", ".join(_res.skipped)))
            _stats = _res.stats
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("analysis.metric_return"), f"{_stats['Return [%]']:.2f}%")
            c2.metric(t("analysis.metric_sharpe"), f"{_stats['Sharpe Ratio']:.2f}")
            c3.metric(t("analysis.metric_mdd"), f"{_stats['Max. Drawdown [%]']:.2f}%")
            c4.metric(t("analysis.metric_final_eq"), f"{_stats['Final Equity']:,.0f}")

            _eq = _res.equity
            _roll_max = _eq.cummax()
            _dd = ((_eq / _roll_max) - 1) * 100
            _fig = go.Figure()
            _fig.add_trace(go.Scatter(x=_eq.index, y=_eq.values, name=t("analysis.equity_label")))
            _fig.add_trace(
                go.Scatter(x=_eq.index, y=_dd.values, name=t("analysis.drawdown_label"), yaxis="y2")
            )
            _fig.update_layout(
                height=400,
                yaxis=dict(title=t("analysis.equity_label")),
                yaxis2=dict(title=t("analysis.drawdown_label"), overlaying="y", side="right"),
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
                with st.expander(t("analysis.per_ticker_results")):
                    st.dataframe(pd.DataFrame(per_rows), width="stretch")

            if st.button(t("analysis.explain_btn")):
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
                    t("analysis.clear_explain"),
                    key="clear_analysis_explain_portfolio",
                    on_click=_pop_ss,
                    args=("_analysis_explain",),
                )

with st.expander(t("analysis.raw_data")):
    st.dataframe(df.tail(100))
