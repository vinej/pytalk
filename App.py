from __future__ import annotations

import logging

import streamlit as st

# Silence the benign "widget created with default value but also had its value
# set via Session State API" warning — triggered by our cross-page preservation
# loop. The widgets still work correctly (session-state wins, default is ignored).
logging.getLogger("streamlit.elements.lib.policies").setLevel(logging.ERROR)

st.set_page_config(page_title="PyTalk", page_icon="assets/favicon.svg", layout="wide")


def _allowed_emails() -> set[str]:
    raw = st.secrets.get("access", {}).get("allowed_emails", [])
    return {str(e).strip().lower() for e in raw if e}


# ── Auth gate ────────────────────────────────────────────────────────────────
if not st.user.is_logged_in:
    st.title("PyTalk")
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

# Preserve widget state across page navigation. Runs on EVERY page render so
# keys from views that aren't currently active (e.g. Analysis's `Source` radio
# while you're on Info) don't get garbage-collected by Streamlit.
_BUTTON_HINTS = (
    "_rm_", "_back_", "_add", "_save", "_del_", "_explain",
    "save_", "del_", "clear_", "FormSubmitter",
)
for _k in list(st.session_state.keys()):
    if any(_h in _k for _h in _BUTTON_HINTS):
        continue
    try:
        st.session_state[_k] = st.session_state[_k]
    except Exception:
        pass

nav = st.navigation(
    [
        st.Page("views/brand.py", title="PyTalk", icon="📈", default=True),
        st.Page("views/analysis.py", title="Analysis"),
        st.Page("views/portfolios.py", title="Portfolios"),
        st.Page("views/custom_tickers.py", title="Custom Tickers"),
        st.Page("views/screener.py", title="Screener"),
        st.Page("views/learning.py", title="Learning"),
        st.Page("views/info.py", title="Info"),
        st.Page("views/logout.py", title="Logout", icon=":material/logout:"),
    ],
    position="top",
)

# Show the sidebar illustration on pages that don't fill the sidebar with
# their own widgets — keeps the panel open and adds a nice brand touch.
_PAGES_WITH_SIDEBAR_WIDGETS = {"Analysis", "Screener"}
if nav.title not in _PAGES_WITH_SIDEBAR_WIDGETS:
    st.sidebar.image("assets/sidebar-art.svg", width=180)

nav.run()
