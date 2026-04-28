"""Portfolios view — create new portfolios and edit existing ones.

State model: each editable portfolio (creation form OR an existing portfolio's
expander) keeps its own list of "row dicts" in `st.session_state` under a
unique state_key. A row dict has shape:
    {id, category, ticker, weight, shares, buy_date, custom}
The list is mutated in place during a render (delete a row, change a ticker,
flip the custom flag) and Streamlit reruns to reflect changes.

When the user clicks Save we materialize the row list into Holding objects and
persist via `save_portfolio` (one DELETE-then-INSERT transaction for atomicity).

See ARCHITECTURE.md → "Streamlit execution model" for why state_key + st.rerun
is the natural pattern here.
"""
from __future__ import annotations

import uuid
from datetime import date

import streamlit as st

from pytalk.auth import current_user
from pytalk.custom_tickers import combined_label, combined_symbols
from pytalk.i18n import category_label, t
from pytalk.llm import build_validate_portfolio_prompt
from pytalk.portfolios import (
    Holding,
    Portfolio,
    delete_portfolio,
    get_all_portfolios,
    save_portfolio,
)
from pytalk.ui import render_llm_block
from pytalk.universe import CATEGORIES, CUSTOM_CATEGORY, OTHER, label, tickers

# Holdings have a real asset class — the meta "Custom Ticker" category is for
# the Custom Tickers list page, not for individual holdings.
_ROW_CATEGORIES = [c for c in CATEGORIES if c != CUSTOM_CATEGORY]

CURRENT_USER = current_user()

# Widget-state preservation is handled once in App.py.

st.title(t("nav.portfolios"))


def _blank_row() -> dict:
    default_category = "ETF" if "ETF" in CATEGORIES else CATEGORIES[0]
    symbols = tickers(default_category)
    default_ticker = "CASH.TO" if "CASH.TO" in symbols else (symbols[0] if symbols else "")
    return {
        "id": uuid.uuid4().hex,
        "category": default_category,
        "ticker": default_ticker,
        "weight": 1.0,
        "shares": 0.0,
        "buy_date": date.today().isoformat(),
        "custom": False,
    }


def _init_rows(state_key: str, holdings: list[Holding]) -> None:
    """Seed a portfolio's row state once per session — subsequent reruns reuse
    whatever the user has edited. The `custom` flag flips on for any ticker
    that isn't in the built-in `tickers(category)` list (e.g. user-added)."""
    if state_key in st.session_state:
        return
    st.session_state[state_key] = [
        {
            "id": uuid.uuid4().hex,
            "category": h.category,
            "ticker": h.ticker,
            "weight": h.weight,
            "shares": float(h.shares or 0.0),
            "buy_date": h.buy_date or date.today().isoformat(),
            "custom": h.ticker not in tickers(h.category),
        }
        for h in holdings
    ] or [_blank_row()]


def _holdings_editor(state_key: str) -> list[Holding]:
    rows = st.session_state[state_key]

    hdr = st.columns([3, 4, 2, 2, 1])
    hdr[0].markdown(f"**{t('common.type')}**")
    hdr[1].markdown(f"**{t('common.ticker')}**")
    hdr[2].markdown(f"**{t('portfolios.shares')}**")
    hdr[3].markdown(f"**{t('portfolios.buy_date')}**")
    hdr[4].markdown("&nbsp;")

    to_remove: str | None = None

    for row in rows:
        row.setdefault("custom", False)
        row.setdefault("shares", 0.0)
        row.setdefault("buy_date", date.today().isoformat())
        rid = row["id"]
        cols = st.columns([3, 4, 2, 2, 1])

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
        # This auto-flips when the user changes the category and the existing
        # ticker isn't valid under the new one.
        if row["ticker"] and row["ticker"] not in symbols:
            row["custom"] = True

        # Two render branches:
        #   custom=True  → free-form text input + "↩" button to switch back
        #   custom=False → selectbox of known symbols + the special OTHER sentinel
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

        shares = cols[2].number_input(
            t("portfolios.shares"),
            min_value=0.0,
            value=float(row["shares"]),
            step=1.0,
            key=f"{state_key}_sh_{rid}",
            label_visibility="collapsed",
        )
        row["shares"] = shares

        try:
            _bd_default = date.fromisoformat(row["buy_date"])
        except (ValueError, TypeError):
            _bd_default = date.today()
        bd = cols[3].date_input(
            t("portfolios.buy_date"),
            value=_bd_default,
            max_value=date.today(),
            key=f"{state_key}_bd_{rid}",
            label_visibility="collapsed",
        )
        row["buy_date"] = bd.isoformat() if bd else None

        if cols[4].button("✕", key=f"{state_key}_rm_{rid}", help=t("portfolios.remove")):
            to_remove = rid

    # Mutate-then-rerun pattern: deletions/additions modify session_state and
    # force a fresh render. Doing it inline (without rerun) would render stale
    # state because Streamlit already drew the row above.
    if to_remove is not None:
        st.session_state[state_key] = [r for r in rows if r["id"] != to_remove]
        st.rerun()

    if st.button(t("portfolios.add_holding"), key=f"{state_key}_add"):
        st.session_state[state_key].append(_blank_row())
        st.rerun()

    # Materialize Holding list. Dedupe on ticker so a row with no ticker (just
    # added, not filled in yet) gets dropped, and accidental duplicates collapse.
    seen: set[str] = set()
    holdings: list[Holding] = []
    for row in st.session_state[state_key]:
        if not row["ticker"] or row["ticker"] in seen:
            continue
        seen.add(row["ticker"])
        # weight=1.0 is a legacy fallback used only when shares aren't set.
        # New rows always have shares; weight stays informational.
        holdings.append(
            Holding(
                ticker=row["ticker"],
                category=row["category"],
                weight=float(row.get("weight", 1.0)),
                shares=float(row.get("shares", 0.0) or 0.0),
                buy_date=row.get("buy_date") or None,
            )
        )
    return holdings


# ── Create new portfolio ────────────────────────────────────────────────────
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

# ── Existing portfolios ─────────────────────────────────────────────────────
# `get_all_portfolios` fetches every portfolio + holdings in 2 queries instead
# of 1+N — important on Turso where each query is an HTTP roundtrip.
st.header(t("portfolios.existing"))

portfolios_all = get_all_portfolios(CURRENT_USER)
if not portfolios_all:
    st.info(t("common.no_portfolios_here"))
    st.stop()

for portfolio in portfolios_all:
    name = portfolio.name
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

        # Weight summary only matters in legacy mode (some holdings missing shares).
        # When every holding has shares, the real weight comes from current prices
        # and is shown on the Analysis page.
        total = sum(h.weight for h in edited)
        if total > 0 and not all(h.shares > 0 and h.buy_date for h in edited):
            normalized = ", ".join(f"{h.ticker}: {h.weight/total:.1%}" for h in edited)
            st.caption(t("portfolios.normalized", text=normalized))

        _can_validate = bool(edited) and total > 0
        render_llm_block(
            f"portfolios_validate_{name}",
            button_label=t("portfolios.validate_btn"),
            clear_label=t("portfolios.clear_validation"),
            prompt_fn=lambda edited=edited, total=total: build_validate_portfolio_prompt(
                name=name,
                holdings=edited,
                weights={h.ticker: h.weight / total for h in edited},
            ),
            can_run=_can_validate,
            blocked_message=t("portfolios.save_first"),
        )
