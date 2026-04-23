from __future__ import annotations

import logging

import streamlit as st

from pytalk.llm import current_model_label

# Silence the benign "widget created with default value but also had its value
# set via Session State API" warning — triggered by our cross-page preservation
# loop. The widgets still work correctly (session-state wins, default is ignored).
logging.getLogger("streamlit.elements.lib.policies").setLevel(logging.ERROR)

st.set_page_config(page_title="pytalk", layout="wide")


def _allowed_emails() -> set[str]:
    raw = st.secrets.get("access", {}).get("allowed_emails", [])
    return {str(e).strip().lower() for e in raw if e}


# ── Auth gate ────────────────────────────────────────────────────────────────
if not st.user.is_logged_in:
    st.title("pytalk")
    st.caption(
        "Family-only access. Sign in with your Microsoft / Hotmail / Outlook account."
    )
    st.button("Sign in with Microsoft", on_click=st.login, type="primary")
    st.stop()

_user_email = (st.user.email or st.user.get("preferred_username", "")).lower().strip()
_allowlist = _allowed_emails()

if _allowlist and _user_email not in _allowlist:
    st.error(
        f"Access denied for **{_user_email or '(unknown email)'}**.\n\n"
        "This app is restricted to a family allowlist. "
        "Ask the app owner to add your email."
    )
    st.button("Sign out", on_click=st.logout)
    st.stop()

# Clear session state if a different user signs in on this browser — prevents
# the previous user's portfolio edits / validations / selections from leaking.
if st.session_state.get("_current_user") != _user_email:
    for _k in list(st.session_state.keys()):
        if _k == "_current_user":
            continue
        try:
            del st.session_state[_k]
        except KeyError:
            pass
    st.session_state["_current_user"] = _user_email

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.caption(f"🧠 Powered by {current_model_label()}")
st.sidebar.caption(f"Signed in as {_user_email}")
st.sidebar.button("Sign out", on_click=st.logout)

nav = st.navigation(
    [
        st.Page("views/analysis.py", title="Analysis", default=True),
        st.Page("views/portfolios.py", title="Portfolios"),
        st.Page("views/screener.py", title="Screener"),
        st.Page("views/learning.py", title="Learning"),
    ]
)
nav.run()
