from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="pytalk", layout="wide")

nav = st.navigation(
    [
        st.Page("views/analysis.py", title="Analysis", default=True),
        st.Page("views/screener.py", title="Screener"),
        st.Page("views/backtest.py", title="Backtest"),
        st.Page("views/portfolios.py", title="Portfolios"),
        st.Page("views/learning.py", title="Learning"),
    ]
)
nav.run()
