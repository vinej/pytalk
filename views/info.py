from __future__ import annotations

import streamlit as st

from pytalk.auth import current_user
from pytalk.i18n import t
from pytalk.llm import current_model_label
from pytalk.portfolios import current_db_label

CURRENT_USER = current_user()


st.title(t("nav.info"))
st.caption(t("info.caption"))

# Session
with st.container(border=True):
    st.subheader(t("info.session"))
    col1, col2 = st.columns([1, 3])
    col1.markdown(f"**{t('info.signed_in')}**")
    col2.markdown(CURRENT_USER)

# Runtime
with st.container(border=True):
    st.subheader(t("info.runtime"))
    col1, col2 = st.columns([1, 3])
    col1.markdown(f"🧠 **{t('info.llm')}**")
    col2.markdown(current_model_label())
    col1, col2 = st.columns([1, 3])
    col1.markdown(f"💾 **{t('info.database')}**")
    col2.markdown(current_db_label())
