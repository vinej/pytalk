from __future__ import annotations

import streamlit as st

from pytalk.i18n import t

st.title(t("logout.title"))
st.warning(t("logout.confirm"))

c_yes, c_no, _ = st.columns([1, 1, 3])
if c_yes.button(t("logout.yes"), type="primary"):
    st.logout()
if c_no.button(t("logout.cancel")):
    st.switch_page("views/analysis.py")
