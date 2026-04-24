from __future__ import annotations

import streamlit as st

from pytalk.custom_tickers import add_ticker, list_user_tickers, remove_ticker
from pytalk.data import detect_category
from pytalk.i18n import category_label, t
from pytalk.universe import CATEGORIES, CUSTOM_CATEGORY

CURRENT_USER = (st.user.email or st.user.get("preferred_username", "")).strip().lower()

# Widget-state preservation is handled once in App.py.


_REAL_CATS = [c for c in CATEGORIES if c != CUSTOM_CATEGORY]


st.title(t("customticker.title"))
st.caption(t("customticker.caption"))

# ── Add form ────────────────────────────────────────────────────────────────
with st.expander(t("customticker.add_header"), expanded=False):
    with st.form("add_custom_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 4, 1])
        _new_symbol = c1.text_input(
            t("customticker.symbol"), placeholder=t("common.ticker_placeholder")
        )
        _new_name = c2.text_input(
            t("customticker.name_opt"), placeholder=t("customticker.name_placeholder")
        )
        _submit = c3.form_submit_button(t("customticker.add"), type="primary")

        if _submit:
            sym = (_new_symbol or "").strip().upper()
            if not sym:
                st.warning(t("customticker.enter_symbol"))
            else:
                with st.spinner(t("customticker.detecting", sym=sym)):
                    cat = detect_category(sym)
                try:
                    add_ticker(CURRENT_USER, cat, sym, name=_new_name.strip())
                    st.success(t("customticker.added", sym=sym, cat=category_label(cat)))
                    st.rerun()
                except Exception as e:
                    st.error(t("customticker.add_failed", error=e))

st.divider()

# ── List + manage ───────────────────────────────────────────────────────────
_user_customs = list_user_tickers(CURRENT_USER)

if not _user_customs:
    st.info(t("customticker.none_yet"))
    st.stop()

total = sum(len(s) for s in _user_customs.values())
st.subheader(t("customticker.list_title", total=total))
st.caption(t("customticker.list_caption"))

for _cat in sorted(_user_customs.keys()):
    _syms = _user_customs[_cat]
    if not _syms:
        continue
    with st.container(border=True):
        st.markdown(t("customticker.cat_line", cat=category_label(_cat), n=len(_syms)))
        for _sym, _name in _syms.items():
            _cols = st.columns([5, 2, 1])
            _label = f"**{_sym}**" + (f" — {_name}" if _name else "")
            _cols[0].markdown(_label)
            _new_cat = _cols[1].selectbox(
                t("customticker.category"),
                _REAL_CATS,
                index=_REAL_CATS.index(_cat) if _cat in _REAL_CATS else 0,
                format_func=category_label,
                key=f"ct_cat_{_cat}_{_sym}",
                label_visibility="collapsed",
            )
            if _new_cat != _cat:
                remove_ticker(CURRENT_USER, _cat, _sym)
                add_ticker(CURRENT_USER, _new_cat, _sym, name=_name)
                st.rerun()
            if _cols[2].button(
                "✕",
                key=f"ct_del_{_cat}_{_sym}",
                help=t("customticker.remove_help", sym=_sym),
            ):
                remove_ticker(CURRENT_USER, _cat, _sym)
                st.rerun()
