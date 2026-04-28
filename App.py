"""PyTalk entry point.

Top-to-bottom flow on every Streamlit rerun:
    1. set_page_config           — must be the first Streamlit call
    2. Auth gate                 — st.user.is_logged_in, then email allowlist
    3. Cross-user session reset  — wipe state when a different user signs in
    4. Widget-state preservation — keep cross-page widget values alive
    5. Multi-page navigation     — one st.Page per views/*.py
    6. Sidebar branding + lang selector

See ARCHITECTURE.md for the full picture (auth, persistence, i18n).
"""
from __future__ import annotations

import logging

import streamlit as st

from pytalk.i18n import language_selector, t

# Silence the benign "widget created with default value but also had its value
# set via Session State API" warning — triggered by our cross-page preservation
# loop. The widgets still work correctly (session-state wins, default is ignored).
logging.getLogger("streamlit.elements.lib.policies").setLevel(logging.ERROR)

# MUST be the first Streamlit call — Streamlit raises if widgets/output happen first.
st.set_page_config(page_title="PyTalk", page_icon="assets/favicon.svg", layout="wide")


def _allowed_emails() -> set[str]:
    """Family allowlist from secrets.toml — empty list disables the gate (anyone
    with a valid OIDC login can enter)."""
    raw = st.secrets.get("access", {}).get("allowed_emails", [])
    return {str(e).strip().lower() for e in raw if e}


# ── Auth gate ────────────────────────────────────────────────────────────────
# Microsoft consumer OIDC (configured in [auth] in secrets.toml). st.stop() halts
# the script — nothing below this block runs until the user is signed in AND
# their email is on the allowlist.
if not st.user.is_logged_in:
    language_selector()
    st.title("PyTalk")
    st.caption(t("auth.caption"))
    st.button(t("auth.signin"), on_click=st.login, type="primary")
    st.stop()

# Microsoft sometimes only sends one of `email` / `preferred_username` depending
# on the account type — try email first, fall back to preferred_username.
_user_email = (st.user.email or st.user.get("preferred_username", "")).lower().strip()
_allowlist = _allowed_emails()

if _allowlist and _user_email not in _allowlist:
    language_selector()
    st.error(t("auth.denied", email=_user_email or t("auth.unknown_email")))
    st.button(t("auth.signout"), on_click=st.logout)
    st.stop()

# ── Cross-user session reset ────────────────────────────────────────────────
# Clear session state if a different user signs in on this browser — prevents
# the previous user's portfolio edits / form values / cached LLM responses from
# leaking visually. The `_current_user` sentinel is what we compare against.
if st.session_state.get("_current_user") != _user_email:
    for _k in list(st.session_state.keys()):
        if _k == "_current_user":
            continue
        try:
            del st.session_state[_k]
        except KeyError:
            pass
    st.session_state["_current_user"] = _user_email

# ── Cross-page widget preservation ──────────────────────────────────────────
# Streamlit garbage-collects session_state keys belonging to widgets that aren't
# rendered on the current page. The loop below "touches" every non-button key
# on every render so widgets on other pages keep their values when you come
# back. Buttons are excluded because re-assigning a button key fires its
# callback on every rerun (infinite loop).
_BUTTON_HINTS = (
    "_rm_", "_back_", "_add", "_save", "_del_", "_explain",
    "save_", "del_", "clear_", "FormSubmitter",
    "validate_btn",
)
for _k in list(st.session_state.keys()):
    if any(_h in _k for _h in _BUTTON_HINTS):
        continue
    try:
        st.session_state[_k] = st.session_state[_k]
    except Exception:
        pass

# ── Navigation ──────────────────────────────────────────────────────────────
nav = st.navigation(
    [
        st.Page("views/brand.py", title="PyTalk", icon="📈", default=True),
        st.Page("views/analysis.py", title=t("nav.analysis")),
        st.Page("views/portfolios.py", title=t("nav.portfolios")),
        st.Page("views/custom_tickers.py", title=t("nav.custom_tickers")),
        st.Page("views/screener.py", title=t("nav.screener")),
        st.Page("views/learning.py", title=t("nav.learning")),
        st.Page("views/info.py", title=t("nav.info")),
        st.Page("views/logout.py", title=t("nav.logout"), icon=":material/logout:"),
    ],
    position="top",
)

# Show the sidebar illustration on pages that don't fill the sidebar with
# their own widgets — keeps the panel open and adds a nice brand touch.
_PAGES_WITH_SIDEBAR_WIDGETS = {t("nav.analysis"), t("nav.screener")}
if nav.title not in _PAGES_WITH_SIDEBAR_WIDGETS:
    st.sidebar.image("assets/sidebar-art.svg", width=180)

language_selector()
nav.run()
