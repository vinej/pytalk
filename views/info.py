from __future__ import annotations

import streamlit as st

from pytalk.llm import current_model_label
from pytalk.portfolios import current_db_label

CURRENT_USER = (st.user.email or st.user.get("preferred_username", "")).strip().lower()


st.title("Info")
st.caption("Who's signed in and what the app is running against right now.")

# Session
with st.container(border=True):
    st.subheader("Session")
    col1, col2 = st.columns([1, 3])
    col1.markdown("**Signed in as**")
    col2.markdown(CURRENT_USER)

# Runtime
with st.container(border=True):
    st.subheader("Runtime")
    col1, col2 = st.columns([1, 3])
    col1.markdown("🧠 **LLM**")
    col2.markdown(current_model_label())
    col1, col2 = st.columns([1, 3])
    col1.markdown("💾 **Database**")
    col2.markdown(current_db_label())
