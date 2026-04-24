from __future__ import annotations

import streamlit as st

from pytalk.custom_tickers import add_ticker, list_user_tickers, remove_ticker
from pytalk.data import detect_category
from pytalk.universe import CATEGORIES, CUSTOM_CATEGORY

CURRENT_USER = (st.user.email or st.user.get("preferred_username", "")).strip().lower()

# Preserve widget state across page navigation.
_BUTTON_HINTS = ("_rm_", "_back_", "_add", "_save", "_del_", "_explain", "save_", "del_", "clear_", "FormSubmitter")
for _k in list(st.session_state.keys()):
    if any(_h in _k for _h in _BUTTON_HINTS):
        continue
    try:
        st.session_state[_k] = st.session_state[_k]
    except Exception:
        pass


_REAL_CATS = [c for c in CATEGORIES if c != CUSTOM_CATEGORY]


st.title("My Custom Tickers")
st.caption(
    "Your saved tickers outside the built-in universe. Tickers are added "
    "automatically when you type one via **Other…** in Analysis — or you can add "
    "them manually below. Yahoo's `quoteType` decides the category."
)

# ── Add form ────────────────────────────────────────────────────────────────
with st.expander("➕ Add a custom ticker manually", expanded=False):
    with st.form("add_custom_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 4, 1])
        _new_symbol = c1.text_input(
            "Symbol", placeholder="e.g. NESN.SW, 0700.HK"
        )
        _new_name = c2.text_input(
            "Name (optional)", placeholder="e.g. Nestle SA"
        )
        _submit = c3.form_submit_button("Add", type="primary")

        if _submit:
            sym = (_new_symbol or "").strip().upper()
            if not sym:
                st.warning("Enter a symbol.")
            else:
                with st.spinner(f"Detecting category for {sym}…"):
                    cat = detect_category(sym)
                try:
                    add_ticker(CURRENT_USER, cat, sym, name=_new_name.strip())
                    st.success(f"Added **{sym}** under **{cat}**.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add: {e}")

st.divider()

# ── List + manage ───────────────────────────────────────────────────────────
_user_customs = list_user_tickers(CURRENT_USER)

if not _user_customs:
    st.info(
        "You haven't added any custom tickers yet. Either use the form above, "
        "or go to **Analysis** → Type = any → Ticker = **Other…** and type a symbol."
    )
    st.stop()

total = sum(len(s) for s in _user_customs.values())
st.subheader(f"Your custom tickers ({total})")
st.caption("Change a ticker's category with the dropdown, or remove with ✕.")

for _cat in sorted(_user_customs.keys()):
    _syms = _user_customs[_cat]
    if not _syms:
        continue
    with st.container(border=True):
        st.markdown(f"**{_cat}** — {len(_syms)} ticker(s)")
        for _sym, _name in _syms.items():
            _cols = st.columns([5, 2, 1])
            _label = f"**{_sym}**" + (f" — {_name}" if _name else "")
            _cols[0].markdown(_label)
            _new_cat = _cols[1].selectbox(
                "Category",
                _REAL_CATS,
                index=_REAL_CATS.index(_cat) if _cat in _REAL_CATS else 0,
                key=f"ct_cat_{_cat}_{_sym}",
                label_visibility="collapsed",
            )
            if _new_cat != _cat:
                remove_ticker(CURRENT_USER, _cat, _sym)
                add_ticker(CURRENT_USER, _new_cat, _sym, name=_name)
                st.rerun()
            if _cols[2].button("✕", key=f"ct_del_{_cat}_{_sym}", help=f"Remove {_sym}"):
                remove_ticker(CURRENT_USER, _cat, _sym)
                st.rerun()
