from __future__ import annotations

import streamlit as st

from pytalk.i18n import t

# This page acts as a brand marker at the left of the top nav.
# Clicking it just lands you on this welcome screen.

_c1, _c2 = st.columns([1, 5])
_c1.image("assets/favicon.svg", width=96)
_c2.title("PyTalk")
_c2.caption(t("brand.caption"))

st.write("")
st.info(
    t("brand.menu_intro")
    + "\n\n"
    + "- " + t("brand.menu_analysis") + "\n"
    + "- " + t("brand.menu_portfolios") + "\n"
    + "- " + t("brand.menu_custom_tickers") + "\n"
    + "- " + t("brand.menu_screener") + "\n"
    + "- " + t("brand.menu_learning") + "\n"
    + "- " + t("brand.menu_info")
)
