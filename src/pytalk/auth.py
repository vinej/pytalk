"""Authenticated user identity helper.

Centralizes the small but easy-to-get-wrong logic of pulling the user's email
from Streamlit's OIDC session — Microsoft consumer accounts sometimes only
return one of `email` or `preferred_username`, so we try both.
"""
from __future__ import annotations

import streamlit as st


def current_user() -> str:
    """Normalized lowercase email of the currently signed-in user.

    Returns an empty string if neither claim is set (which shouldn't happen
    once the auth gate in App.py has passed). Always lowercase + stripped so
    DB lookups and allowlist comparisons are consistent.
    """
    return (st.user.email or st.user.get("preferred_username", "")).strip().lower()
