from __future__ import annotations

import streamlit as st

st.title("Sign out")
st.warning("Are you sure you want to sign out of PyTalk?")

c_yes, c_no, _ = st.columns([1, 1, 3])
if c_yes.button("Yes, sign out", type="primary"):
    st.logout()
if c_no.button("Cancel"):
    st.switch_page("views/analysis.py")
