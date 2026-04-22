from __future__ import annotations

import uuid

import streamlit as st

from pytalk.portfolios import (
    Holding,
    Portfolio,
    delete_portfolio,
    get_portfolio,
    list_portfolios,
    save_portfolio,
)
from pytalk.universe import CATEGORIES, OTHER, label, tickers

# Preserve widget state across page navigation
for _k in list(st.session_state.keys()):
    st.session_state[_k] = st.session_state[_k]

st.title("Portfolios")


def _blank_row() -> dict:
    first_category = CATEGORIES[0]
    return {
        "id": uuid.uuid4().hex,
        "category": first_category,
        "ticker": tickers(first_category)[0],
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
    hdr[0].markdown("**Type**")
    hdr[1].markdown("**Ticker**")
    hdr[2].markdown("**Weight**")
    hdr[3].markdown("&nbsp;")

    to_remove: str | None = None

    for row in rows:
        row.setdefault("custom", False)
        rid = row["id"]
        cols = st.columns([3, 5, 2, 1])

        category = cols[0].selectbox(
            "Type",
            CATEGORIES,
            index=CATEGORIES.index(row["category"]),
            key=f"{state_key}_cat_{rid}",
            label_visibility="collapsed",
        )
        row["category"] = category

        symbols = tickers(category)
        # If stored ticker isn't in this category's list, treat row as custom.
        if row["ticker"] and row["ticker"] not in symbols:
            row["custom"] = True

        if row["custom"]:
            with cols[1]:
                sub = st.columns([5, 1])
                typed = sub[0].text_input(
                    "Ticker",
                    value=row["ticker"],
                    placeholder="Custom symbol",
                    key=f"{state_key}_tkr_custom_{rid}",
                    label_visibility="collapsed",
                ).strip().upper()
                row["ticker"] = typed
                if sub[1].button("↩", key=f"{state_key}_back_{rid}", help="Use picklist"):
                    row["custom"] = False
                    row["ticker"] = symbols[0] if symbols else ""
                    st.rerun()
        else:
            options = symbols + [OTHER]
            default_idx = symbols.index(row["ticker"]) if row["ticker"] in symbols else 0
            choice = cols[1].selectbox(
                "Ticker",
                options,
                index=default_idx,
                format_func=lambda s, c=category: label(c, s),
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
            "Weight",
            min_value=0.0,
            value=float(row["weight"]),
            step=0.1,
            key=f"{state_key}_wt_{rid}",
            label_visibility="collapsed",
        )
        row["weight"] = weight

        if cols[3].button("✕", key=f"{state_key}_rm_{rid}", help="Remove"):
            to_remove = rid

    if to_remove is not None:
        st.session_state[state_key] = [r for r in rows if r["id"] != to_remove]
        st.rerun()

    if st.button("Add holding", key=f"{state_key}_add"):
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


st.header("Create a portfolio")
_init_rows("_create_rows", [])
new_name = st.text_input("Name", placeholder="e.g. Tech Megacaps", key="_create_name")
create_holdings = _holdings_editor("_create_rows")

if st.button("Save portfolio", type="primary", key="_create_save"):
    try:
        save_portfolio(Portfolio(name=new_name.strip(), holdings=create_holdings))
        st.success(f"Saved portfolio “{new_name.strip()}”.")
        st.session_state.pop("_create_rows", None)
        st.session_state.pop("_create_name", None)
        st.rerun()
    except ValueError as e:
        st.error(str(e))

st.divider()
st.header("Existing portfolios")

names = list_portfolios()
if not names:
    st.info("No portfolios yet. Create one above.")
    st.stop()

for name in names:
    portfolio = get_portfolio(name)
    if portfolio is None:
        continue
    with st.expander(f"{name} ({len(portfolio.holdings)} holdings)"):
        state_key = f"_edit_{name}_rows"
        _init_rows(state_key, portfolio.holdings)
        edited = _holdings_editor(state_key)

        col_save, col_delete = st.columns(2)
        if col_save.button("Save changes", key=f"save_{name}", type="primary"):
            try:
                save_portfolio(Portfolio(name=name, holdings=edited))
                st.session_state.pop(state_key, None)
                st.success("Updated.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        if col_delete.button("Delete", key=f"del_{name}"):
            delete_portfolio(name)
            st.session_state.pop(state_key, None)
            st.success(f"Deleted “{name}”.")
            st.rerun()

        total = sum(h.weight for h in edited)
        if total > 0:
            normalized = ", ".join(f"{h.ticker}: {h.weight/total:.1%}" for h in edited)
            st.caption(f"Normalized weights — {normalized}")
