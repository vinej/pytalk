from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pytalk import get_prices, run_backtest, run_portfolio_backtest, run_portfolio_buy_hold
from pytalk.llm import ask_llm_stream, llm_available, unavailable_message
from pytalk.portfolios import get_portfolio, list_portfolios
from pytalk.strategies import STRATEGIES
from pytalk.universe import CATEGORIES, OTHER, label, tickers

# Widget-state preservation is handled once in App.py.

with st.sidebar:
    mode = st.radio(
        "Source",
        ["Single ticker", "Portfolio"],
        horizontal=True,
        key="bt_mode",
    )

    ticker: str | None = None
    category: str | None = None
    portfolio_name: str | None = None

    if mode == "Single ticker":
        category = st.selectbox(
            "Type",
            CATEGORIES,
            index=CATEGORIES.index("Stock"),
            key="bt_category",
        )
        options = tickers(category) + [OTHER]
        choice = st.selectbox(
            "Ticker",
            options,
            format_func=lambda s: label(category, s),
            key=f"bt_ticker_{category}",
        )
        if choice == OTHER:
            ticker = st.text_input(
                "Custom ticker",
                placeholder="e.g. NESN.SW, 0700.HK",
                key="bt_custom_ticker",
            ).strip().upper()
        else:
            ticker = choice
    else:
        portfolio_names = list_portfolios()
        if not portfolio_names:
            st.warning("No portfolios yet. Create one on the Portfolios page.")
        else:
            portfolio_name = st.selectbox(
                "Portfolio", portfolio_names, key="bt_portfolio"
            )

    lookback_days = st.slider(
        "Lookback (days)", 180, 3650, 730, key="bt_lookback"
    )
    end = st.date_input("End date", value=date.today(), key="bt_end")
    start = end - timedelta(days=lookback_days)

    strategy_name = st.selectbox(
        "Strategy", list(STRATEGIES.keys()), key="bt_strategy"
    )
    cash = st.number_input(
        "Starting cash", min_value=1_000, value=10_000, step=1_000, key="bt_cash"
    )
    commission_bps = st.number_input(
        "Commission (bps per trade)", 0, 100, 20, key="bt_commission_bps"
    )

    params: dict[str, float | int] = {}
    rebalance_freq = "none"
    if strategy_name == "Buy & Hold" and mode == "Portfolio":
        _reb_label = st.selectbox(
            "Rebalance frequency",
            ["None (drift)", "Monthly", "Quarterly", "Yearly"],
            index=2,
            key="bt_reb_freq",
        )
        rebalance_freq = {
            "None (drift)": "none",
            "Monthly": "M",
            "Quarterly": "Q",
            "Yearly": "Y",
        }[_reb_label]
    if strategy_name == "Buy & Hold":
        pass  # no other params
    elif strategy_name == "Faber Trend Filter":
        params["window"] = st.slider(
            "SMA window (trading days, ~21 per month)",
            20, 500, 200, key="bt_faber_window"
        )
    elif strategy_name == "SMA Cross":
        params["fast"] = st.slider("Fast SMA", 5, 100, 20, key="bt_sma_fast")
        params["slow"] = st.slider("Slow SMA", 20, 300, 50, key="bt_sma_slow")
    elif strategy_name == "MACD Cross":
        params["fast"] = st.slider("Fast EMA", 5, 50, 12, key="bt_macd_fast")
        params["slow"] = st.slider("Slow EMA", 10, 100, 26, key="bt_macd_slow")
        params["signal"] = st.slider("Signal EMA", 3, 30, 9, key="bt_macd_signal")
    elif strategy_name == "RSI Mean Reversion":
        params["window"] = st.slider("RSI window", 2, 50, 14, key="bt_rsi_window")
        params["oversold"] = st.slider("Oversold", 5, 45, 30, key="bt_rsi_oversold")
        params["overbought"] = st.slider(
            "Overbought", 55, 95, 70, key="bt_rsi_overbought"
        )
    elif strategy_name == "Bollinger Mean Reversion":
        params["window"] = st.slider("Window", 5, 100, 20, key="bt_boll_window")
        params["k"] = st.slider(
            "Std deviations", 1.0, 4.0, 2.0, step=0.1, key="bt_boll_k"
        )
    elif strategy_name == "Donchian Breakout":
        params["entry_window"] = st.slider(
            "Entry window (N-day high)", 5, 100, 20, key="bt_donch_entry"
        )
        params["exit_window"] = st.slider(
            "Exit window (M-day low)", 3, 60, 10, key="bt_donch_exit"
        )
    elif strategy_name == "VWAP Reversion":
        params["window"] = st.slider(
            "VWAP window", 5, 100, 20, key="bt_vwap_window"
        )
        params["k"] = st.slider(
            "Std deviations (entry)", 0.5, 4.0, 1.5, step=0.1, key="bt_vwap_k"
        )

    run = st.button("Run backtest", type="primary")
    if st.button("Clear results"):
        st.session_state.pop("_bt_result", None)
        st.rerun()

commission = commission_bps / 10_000
strategy = STRATEGIES[strategy_name]


def _equity_figure(equity_index, equity_values, drawdown_pct=None) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_index, y=equity_values, name="Equity"))
    layout = dict(height=500, yaxis=dict(title="Equity"))
    if drawdown_pct is not None:
        fig.add_trace(
            go.Scatter(x=equity_index, y=drawdown_pct, name="Drawdown %", yaxis="y2")
        )
        layout["yaxis2"] = dict(title="Drawdown %", overlaying="y", side="right")
    fig.update_layout(**layout)
    return fig


if run:
    if mode == "Single ticker":
        if not ticker:
            st.error("Pick a ticker.")
            st.stop()
        with st.spinner(f"Loading {ticker}…"):
            prices = get_prices(ticker, start, end)
        if prices.empty:
            st.error(f"No data for {ticker} in the selected range.")
            st.stop()
        with st.spinner("Running backtest…"):
            result = run_backtest(
                prices, strategy, cash=float(cash), commission=commission, **params
            )
        st.session_state["_bt_result"] = {
            "mode": "Single ticker",
            "strategy_name": strategy_name,
            "category": category,
            "ticker": ticker,
            "result": result,
        }
    else:
        if not portfolio_name:
            st.error("Pick a portfolio.")
            st.stop()
        portfolio = get_portfolio(portfolio_name)
        if portfolio is None or not portfolio.holdings:
            st.error(f"Portfolio “{portfolio_name}” has no holdings.")
            st.stop()
        with st.spinner("Loading prices…"):
            prices_by_ticker: dict[str, pd.DataFrame] = {}
            weights: dict[str, float] = {}
            for h in portfolio.holdings:
                prices_by_ticker[h.ticker] = get_prices(h.ticker, start, end)
                weights[h.ticker] = h.weight
        with st.spinner("Running backtest…"):
            try:
                if strategy_name == "Buy & Hold":
                    portfolio_result = run_portfolio_buy_hold(
                        prices_by_ticker,
                        weights,
                        cash=float(cash),
                        commission=commission,
                        rebalance_freq=rebalance_freq,
                    )
                else:
                    portfolio_result = run_portfolio_backtest(
                        prices_by_ticker,
                        weights,
                        strategy,
                        cash=float(cash),
                        commission=commission,
                        **params,
                    )
            except ValueError as e:
                st.error(str(e))
                st.stop()
        st.session_state["_bt_result"] = {
            "mode": "Portfolio",
            "strategy_name": strategy_name,
            "portfolio_name": portfolio_name,
            "result": portfolio_result,
        }

snapshot = st.session_state.get("_bt_result")
if snapshot is None:
    st.info("Configure parameters in the sidebar, then click Run backtest.")
    st.stop()

bt_mode = snapshot["mode"]
bt_strategy = snapshot["strategy_name"]

if bt_mode == "Single ticker":
    bt_ticker = snapshot["ticker"]
    bt_category = snapshot["category"]
    result = snapshot["result"]

    st.title(f"Backtest for {label(bt_category, bt_ticker)} with {bt_strategy}")

    stats = result.stats
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Return", f"{stats['Return [%]']:.2f}%")
    c2.metric("Buy & Hold", f"{stats['Buy & Hold Return [%]']:.2f}%")
    c3.metric("Sharpe", f"{stats['Sharpe Ratio']:.2f}")
    c4.metric("Max Drawdown", f"{stats['Max. Drawdown [%]']:.2f}%")

    equity = result.equity_curve
    st.plotly_chart(
        _equity_figure(equity.index, equity["Equity"], equity["DrawdownPct"] * 100),
        width="stretch",
    )

    if st.button("🧠 Explain this result"):
        if not llm_available():
            st.error(unavailable_message())
        else:
            prompt = f"""Explain this backtest result for a retail investor.

Strategy: {bt_strategy}
Ticker: {bt_ticker} ({bt_category})
Return: {stats['Return [%]']:.2f}%
Buy & Hold return: {stats['Buy & Hold Return [%]']:.2f}%
Sharpe Ratio: {stats['Sharpe Ratio']:.2f}
Max Drawdown: {stats['Max. Drawdown [%]']:.2f}%
Number of trades: {int(stats.get('# Trades', 0))}
Win rate: {float(stats.get('Win Rate [%]', 0)):.1f}%

Respond as a markdown numbered list — one short sentence per point, no introduction, no final paragraph:
1. Did the strategy beat buy-and-hold? By how much?
2. Was the risk-adjusted return (Sharpe) reasonable?
3. Was the drawdown psychologically tradeable?
4. One honest caveat (overfitting, small sample, single-asset, etc.)
"""
            with st.container(border=True):
                st.write_stream(ask_llm_stream(prompt))

    st.subheader("Trades")
    st.dataframe(result.trades)

    with st.expander("Full stats"):
        st.dataframe(stats.astype(str).to_frame("value"))

else:
    bt_portfolio_name = snapshot["portfolio_name"]
    portfolio_result = snapshot["result"]

    st.title(f"Backtest for portfolio “{bt_portfolio_name}” with {bt_strategy}")

    if portfolio_result.skipped:
        st.warning(
            "Skipped (no data or failed backtest): "
            + ", ".join(portfolio_result.skipped)
        )

    stats = portfolio_result.stats
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Return", f"{stats['Return [%]']:.2f}%")
    c2.metric("Sharpe", f"{stats['Sharpe Ratio']:.2f}")
    c3.metric("Max Drawdown", f"{stats['Max. Drawdown [%]']:.2f}%")
    c4.metric("Final Equity", f"{stats['Final Equity']:,.0f}")

    equity = portfolio_result.equity
    roll_max = equity.cummax()
    drawdown_pct = ((equity / roll_max) - 1) * 100
    st.plotly_chart(
        _equity_figure(equity.index, equity.values, drawdown_pct.values),
        width="stretch",
    )

    st.subheader("Per-ticker results")
    per_ticker_rows = []
    for tkr, per_result in portfolio_result.per_ticker.items():
        s = per_result.stats
        per_ticker_rows.append(
            {
                "Ticker": tkr,
                "Weight": f"{portfolio_result.weights[tkr]:.1%}",
                "Return [%]": round(float(s["Return [%]"]), 2),
                "Buy & Hold [%]": round(float(s["Buy & Hold Return [%]"]), 2),
                "Sharpe": round(float(s["Sharpe Ratio"]), 2),
                "Max DD [%]": round(float(s["Max. Drawdown [%]"]), 2),
                "# Trades": int(s.get("# Trades", 0)),
            }
        )
    per_ticker_df = pd.DataFrame(per_ticker_rows)
    st.dataframe(per_ticker_df, width="stretch")

    if st.button("🧠 Explain this result"):
        if not llm_available():
            st.error(unavailable_message())
        else:
            per_ticker_text = "\n".join(
                f"  {r['Ticker']} (weight {r['Weight']}): "
                f"return {r['Return [%]']}%, B&H {r['Buy & Hold [%]']}%, "
                f"Sharpe {r['Sharpe']}, DD {r['Max DD [%]']}%"
                for r in per_ticker_rows
            )
            prompt = f"""Explain this portfolio backtest for a retail investor.

Portfolio: {bt_portfolio_name}
Strategy applied to each holding: {bt_strategy}
Aggregate return: {stats['Return [%]']:.2f}%
Aggregate Sharpe: {stats['Sharpe Ratio']:.2f}
Aggregate Max Drawdown: {stats['Max. Drawdown [%]']:.2f}%
Final equity: {stats['Final Equity']:,.0f}

Per-ticker results:
{per_ticker_text}

Respond as a markdown numbered list — one short sentence per point, no introduction, no final paragraph:
1. Did the portfolio-level strategy produce a reasonable risk-adjusted return?
2. Which holdings carried the portfolio? Which ones hurt it?
3. Was the diversification helpful (lower drawdown than any single name)?
4. One honest caveat about applying the same strategy to very different assets.
"""
            with st.container(border=True):
                st.write_stream(ask_llm_stream(prompt))

    with st.expander("Per-ticker trades"):
        for tkr, per_result in portfolio_result.per_ticker.items():
            st.markdown(f"**{tkr}**")
            st.dataframe(per_result.trades, width="stretch")

    with st.expander("Portfolio stats"):
        st.dataframe(stats.astype(str).to_frame("value"))
