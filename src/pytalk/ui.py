"""Shared Streamlit UI helpers used across views."""
from __future__ import annotations

from typing import Callable

import streamlit as st

from pytalk.llm import ask_llm_stream, llm_available, unavailable_message


def pop_ss(key: str) -> None:
    """Drop a session_state key, used as `on_click` for "clear" buttons.

    Safe to call when the key is missing.
    """
    st.session_state.pop(key, None)


def render_llm_block(
    key_prefix: str,
    *,
    button_label: str,
    clear_label: str,
    prompt_fn: Callable[[], str],
    can_run: bool = True,
    blocked_message: str | None = None,
) -> None:
    """The standard click-to-ask-LLM UI block.

    Behavior:
        - Renders an action button.
        - On click (and `can_run`), streams the LLM response into a bordered
          container and caches the result in session_state.
        - On subsequent reruns, re-renders the cached response from the same key.
        - Renders a clear button whenever a cached response exists.

    `prompt_fn` is called only when the user clicks the button — this lets
    callers avoid expensive prompt-building work on every rerun.

    `key_prefix` must be unique across the app (e.g. include the portfolio
    name or ticker symbol).
    """
    storage_key = f"_llm_{key_prefix}"
    if st.button(button_label, key=f"btn_{key_prefix}"):
        if not can_run:
            st.warning(blocked_message or "")
        elif not llm_available():
            st.error(unavailable_message())
        else:
            with st.container(border=True):
                full = st.write_stream(ask_llm_stream(prompt_fn()))
            st.session_state[storage_key] = full
    else:
        stored = st.session_state.get(storage_key)
        if stored:
            with st.container(border=True):
                st.markdown(stored)

    if st.session_state.get(storage_key):
        st.button(
            clear_label,
            key=f"clear_{key_prefix}",
            on_click=pop_ss,
            args=(storage_key,),
        )
