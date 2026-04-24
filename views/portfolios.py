from __future__ import annotations

import uuid

import streamlit as st

from pytalk.custom_tickers import combined_label, combined_symbols
from pytalk.i18n import category_label, t
from pytalk.llm import ask_llm_stream, llm_available, unavailable_message
from pytalk.portfolios import (
    Holding,
    Portfolio,
    delete_portfolio,
    get_portfolio,
    list_portfolios,
    save_portfolio,
)
from pytalk.universe import CATEGORIES, CUSTOM_CATEGORY, OTHER, UNIVERSE, label, tickers

# Portfolio holdings should have a real asset class, not the meta "Custom Ticker"
_ROW_CATEGORIES = [c for c in CATEGORIES if c != CUSTOM_CATEGORY]

CURRENT_USER = (st.user.email or st.user.get("preferred_username", "")).strip().lower()

# Widget-state preservation is handled once in App.py.

st.title(t("nav.portfolios"))


def _pop_ss(key: str) -> None:
    """Callback helper — drops a session_state key before Streamlit's auto-rerun."""
    st.session_state.pop(key, None)


def _blank_row() -> dict:
    default_category = "ETF" if "ETF" in CATEGORIES else CATEGORIES[0]
    symbols = tickers(default_category)
    default_ticker = "CASH.TO" if "CASH.TO" in symbols else (symbols[0] if symbols else "")
    return {
        "id": uuid.uuid4().hex,
        "category": default_category,
        "ticker": default_ticker,
        "weight": 1.0,
        "custom": False,
    }


def _init_rows(state_key: str, holdings: list[Holding]) -> None:
    if state_key in st.session_state:
        return
    st.session_state[state_key] = [
        {
            "id": uuid.uuid4().hex,
            "category": h.category,
            "ticker": h.ticker,
            "weight": h.weight,
            "custom": h.ticker not in tickers(h.category),
        }
        for h in holdings
    ] or [_blank_row()]


def _holdings_editor(state_key: str) -> list[Holding]:
    rows = st.session_state[state_key]

    hdr = st.columns([3, 5, 2, 1])
    hdr[0].markdown(f"**{t('common.type')}**")
    hdr[1].markdown(f"**{t('common.ticker')}**")
    hdr[2].markdown(f"**{t('portfolios.weight')}**")
    hdr[3].markdown("&nbsp;")

    to_remove: str | None = None

    for row in rows:
        row.setdefault("custom", False)
        rid = row["id"]
        cols = st.columns([3, 5, 2, 1])

        _cur = row["category"] if row["category"] in _ROW_CATEGORIES else _ROW_CATEGORIES[0]
        category = cols[0].selectbox(
            t("common.type"),
            _ROW_CATEGORIES,
            index=_ROW_CATEGORIES.index(_cur),
            format_func=category_label,
            key=f"{state_key}_cat_{rid}",
            label_visibility="collapsed",
        )
        row["category"] = category

        symbols = combined_symbols(CURRENT_USER, category)
        # If stored ticker isn't in this category's list, treat row as custom.
        if row["ticker"] and row["ticker"] not in symbols:
            row["custom"] = True

        if row["custom"]:
            with cols[1]:
                sub = st.columns([5, 1])
                typed = sub[0].text_input(
                    t("common.ticker"),
                    value=row["ticker"],
                    placeholder=t("portfolios.custom_placeholder"),
                    key=f"{state_key}_tkr_custom_{rid}",
                    label_visibility="collapsed",
                ).strip().upper()
                row["ticker"] = typed
                if sub[1].button(
                    "↩",
                    key=f"{state_key}_back_{rid}",
                    help=t("portfolios.use_picklist"),
                ):
                    row["custom"] = False
                    row["ticker"] = symbols[0] if symbols else ""
                    st.rerun()
        else:
            options = symbols + [OTHER]
            default_idx = symbols.index(row["ticker"]) if row["ticker"] in symbols else 0
            choice = cols[1].selectbox(
                t("common.ticker"),
                options,
                index=default_idx,
                format_func=lambda s, c=category: combined_label(CURRENT_USER, c, s),
                key=f"{state_key}_tkr_{rid}_{category}",
                label_visibility="collapsed",
            )
            if choice == OTHER:
                row["custom"] = True
                row["ticker"] = ""
                st.rerun()
            else:
                row["ticker"] = choice

        weight = cols[2].number_input(
            t("portfolios.weight"),
            min_value=0.0,
            value=float(row["weight"]),
            step=0.1,
            key=f"{state_key}_wt_{rid}",
            label_visibility="collapsed",
        )
        row["weight"] = weight

        if cols[3].button("✕", key=f"{state_key}_rm_{rid}", help=t("portfolios.remove")):
            to_remove = rid

    if to_remove is not None:
        st.session_state[state_key] = [r for r in rows if r["id"] != to_remove]
        st.rerun()

    if st.button(t("portfolios.add_holding"), key=f"{state_key}_add"):
        st.session_state[state_key].append(_blank_row())
        st.rerun()

    seen: set[str] = set()
    holdings: list[Holding] = []
    for row in st.session_state[state_key]:
        if not row["ticker"] or row["ticker"] in seen:
            continue
        seen.add(row["ticker"])
        holdings.append(
            Holding(ticker=row["ticker"], category=row["category"], weight=float(row["weight"]))
        )
    return holdings


st.header(t("portfolios.create_header"))
_init_rows("_create_rows", [])
new_name = st.text_input(
    t("portfolios.name"),
    placeholder=t("portfolios.name_placeholder"),
    key="_create_name",
)
create_holdings = _holdings_editor("_create_rows")

if st.button(t("portfolios.save"), type="primary", key="_create_save"):
    try:
        save_portfolio(CURRENT_USER, Portfolio(name=new_name.strip(), holdings=create_holdings))
        st.success(t("portfolios.saved", name=new_name.strip()))
        st.session_state.pop("_create_rows", None)
        st.session_state.pop("_create_name", None)
        st.rerun()
    except ValueError as e:
        st.error(str(e))

st.divider()
st.header(t("portfolios.existing"))

names = list_portfolios(CURRENT_USER)
if not names:
    st.info(t("common.no_portfolios_here"))
    st.stop()

for name in names:
    portfolio = get_portfolio(CURRENT_USER, name)
    if portfolio is None:
        continue
    with st.expander(t("portfolios.expander", name=name, count=len(portfolio.holdings))):
        state_key = f"_edit_{name}_rows"
        _init_rows(state_key, portfolio.holdings)
        edited = _holdings_editor(state_key)

        col_save, col_delete = st.columns(2)
        if col_save.button(t("portfolios.save_changes"), key=f"save_{name}", type="primary"):
            try:
                save_portfolio(CURRENT_USER, Portfolio(name=name, holdings=edited))
                st.session_state.pop(state_key, None)
                st.success(t("portfolios.updated"))
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        if col_delete.button(t("portfolios.delete"), key=f"del_{name}"):
            delete_portfolio(CURRENT_USER, name)
            st.session_state.pop(state_key, None)
            st.success(t("portfolios.deleted", name=name))
            st.rerun()

        total = sum(h.weight for h in edited)
        if total > 0:
            normalized = ", ".join(f"{h.ticker}: {h.weight/total:.1%}" for h in edited)
            st.caption(t("portfolios.normalized", text=normalized))

        _validate_key = f"_portfolios_validate_{name}"
        if st.button(t("portfolios.validate_btn")):
            if not llm_available():
                st.error(unavailable_message())
            elif not edited or total <= 0:
                st.warning(t("portfolios.save_first"))
            else:
                holdings_text = "\n".join(
                    f"  - {h.ticker} ({h.category}) "
                    f"[{UNIVERSE.get(h.category, {}).get(h.ticker) or 'custom'}] — "
                    f"{h.weight/total:.1%}"
                    for h in edited
                )
                by_type = {}
                for h in edited:
                    by_type[h.category] = by_type.get(h.category, 0.0) + h.weight / total
                mix_text = ", ".join(f"{t}: {w:.1%}" for t, w in by_type.items())

                prompt = f"""Review this portfolio structure.

Name: {name}
Total holdings: {len(edited)}
Asset-type mix: {mix_text}

Holdings:
{holdings_text}

Respond as a markdown numbered list — one short sentence per point, no introduction, no final paragraph:
1. Overall diversification — across asset classes, geography, and sectors.
2. Concentration risks — any single holding or type too dominant?
3. Overlap — do multiple holdings track the same thing (e.g. two S&P 500 ETFs)?
4. What kind of investor this portfolio suits (growth / income / capital preservation).
5. One honest caveat (hidden correlations, home-bias, missing asset classes, etc.).
6. One constructive observation — what would make it more robust, without recommending specific tickers.

Don't invent facts about any holding you don't recognise; just say "unfamiliar".
"""
                with st.container(border=True):
                    _full = st.write_stream(ask_llm_stream(prompt))
                st.session_state[_validate_key] = _full
        else:
            _stored = st.session_state.get(_validate_key)
            if _stored:
                with st.container(border=True):
                    st.markdown(_stored)

        if st.session_state.get(_validate_key):
            st.button(
                t("portfolios.clear_validation"),
                key=f"clear_portfolios_validate_{name}",
                on_click=_pop_ss,
                args=(_validate_key,),
            )
