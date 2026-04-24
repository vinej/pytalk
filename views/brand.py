from __future__ import annotations

import streamlit as st

# This page acts as a brand marker at the left of the top nav.
# Clicking it just lands you on this welcome screen.

_c1, _c2 = st.columns([1, 5])
_c1.image("assets/favicon.svg", width=96)
_c2.title("PyTalk")
_c2.caption("Personal finance analysis — family edition.")

st.write("")
st.info(
    "Pick a section from the menu above:\n\n"
    "- **Analysis** — chart a ticker or a portfolio, run a backtest, get LLM commentary\n"
    "- **Portfolios** — create and edit your own portfolios\n"
    "- **Custom Tickers** — add tickers outside the built-in universe\n"
    "- **Screener** — filter the universe by past performance and indicators\n"
    "- **Learning** — how each strategy works and when it makes sense\n"
    "- **Info** — your session and runtime config"
)
