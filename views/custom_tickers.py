from __future__ import annotations

import requests
import streamlit as st

from pytalk.custom_tickers import add_ticker, list_user_tickers, remove_ticker
from pytalk.data import detect_category
from pytalk.i18n import category_label, t
from pytalk.universe import CATEGORIES, CUSTOM_CATEGORY


@st.cache_data(ttl=600, show_spinner=False)
def _search_yahoo(query: str, max_results: int = 10) -> list[dict]:
    """Hit Yahoo's documented search endpoint. Returns [] on any error."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": q, "quotesCount": max_results, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0 (PyTalk family edition)"},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [{"_error": str(e)}]
    out: list[dict] = []
    for item in data.get("quotes", [])[:max_results]:
        sym = item.get("symbol")
        if not sym:
            continue
        out.append({
            "symbol":   sym,
            "name":     item.get("longname") or item.get("shortname") or "",
            "exchange": item.get("exchDisp") or item.get("exchange") or "",
            "type":     item.get("typeDisp") or item.get("quoteType") or "",
        })
    return out

CURRENT_USER = (st.user.email or st.user.get("preferred_username", "")).strip().lower()

# Widget-state preservation is handled once in App.py.


_REAL_CATS = [c for c in CATEGORIES if c != CUSTOM_CATEGORY]


st.title(t("customticker.title"))
st.caption(t("customticker.caption"))

with st.expander(t("customticker.help_header"), expanded=False):
    st.markdown(t("customticker.help_body"))

# ── Yahoo Finance search ────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader(t("customticker.search_header"))
    _search_q = st.text_input(
        t("customticker.search_label"),
        placeholder=t("customticker.search_placeholder"),
        key="ct_search_q",
    )
    if _search_q:
        _hits = _search_yahoo(_search_q)
        if _hits and "_error" in _hits[0]:
            st.error(t("customticker.search_error", error=_hits[0]["_error"]))
        elif not _hits:
            st.caption(t("customticker.search_no_results"))
        else:
            _hdr = st.columns([2, 5, 2, 2, 1])
            _hdr[0].markdown(f"**{t('customticker.symbol')}**")
            _hdr[1].markdown(f"**{t('customticker.col_name')}**")
            _hdr[2].markdown(f"**{t('customticker.col_exchange')}**")
            _hdr[3].markdown(f"**{t('customticker.col_type')}**")
            _hdr[4].markdown("&nbsp;")
            for _hit in _hits:
                _row = st.columns([2, 5, 2, 2, 1])
                _row[0].markdown(f"`{_hit['symbol']}`")
                _row[1].write(_hit["name"])
                _row[2].caption(_hit["exchange"])
                _row[3].caption(_hit["type"])
                if _row[4].button(
                    t("customticker.add_short"),
                    key=f"ct_search_add_{_hit['symbol']}",
                ):
                    sym = _hit["symbol"].strip().upper()
                    with st.spinner(t("customticker.detecting", sym=sym)):
                        cat = detect_category(sym)
                    try:
                        add_ticker(CURRENT_USER, cat, sym, name=_hit["name"])
                        st.success(t("customticker.added", sym=sym, cat=category_label(cat)))
                        st.rerun()
                    except Exception as e:
                        st.error(t("customticker.add_failed", error=e))

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
