"""Per-user custom tickers — auto-saved when a user types one via 'Other…'.

Merges with the hard-coded UNIVERSE so custom tickers appear in every picker
automatically on subsequent visits.
"""
from __future__ import annotations

from pytalk._storage import connect, ensure_schema, write_tx
from pytalk.universe import CUSTOM_CATEGORY, OTHER, UNIVERSE

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS user_tickers (
        user_email TEXT NOT NULL,
        category   TEXT NOT NULL,
        symbol     TEXT NOT NULL,
        name       TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_email, category, symbol)
    )
    """,
]


def _connect():
    con = connect()
    ensure_schema(con, _SCHEMA_STATEMENTS)
    return con


def _norm(user_email: str) -> str:
    return (user_email or "").strip().lower()


def _cache_key(email: str) -> str:
    return f"_pytalk_user_tickers_cache::{email}"


def _invalidate_cache(email: str) -> None:
    try:
        import streamlit as st  # noqa: PLC0415

        st.session_state.pop(_cache_key(email), None)
    except Exception:
        pass


# ── CRUD ─────────────────────────────────────────────────────────────────────


def add_ticker(user_email: str, category: str, symbol: str, name: str = "") -> None:
    """Insert-or-update a user's custom ticker. Idempotent: re-adding updates the name."""
    e = _norm(user_email)
    sym = (symbol or "").strip().upper()
    if not e or not sym:
        return
    # Skip if already in the hard-coded universe for this category
    if sym in UNIVERSE.get(category, {}):
        return
    con = _connect()
    try:
        write_tx(
            con,
            [
                (
                    "INSERT INTO user_tickers (user_email, category, symbol, name) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (user_email, category, symbol) DO UPDATE SET name = excluded.name",
                    (e, category, sym, (name or "").strip()),
                )
            ],
        )
    finally:
        con.close()
    _invalidate_cache(e)


def remove_ticker(user_email: str, category: str, symbol: str) -> None:
    e = _norm(user_email)
    con = _connect()
    try:
        write_tx(
            con,
            [
                (
                    "DELETE FROM user_tickers "
                    "WHERE user_email = ? AND category = ? AND symbol = ?",
                    (e, category, (symbol or "").strip().upper()),
                )
            ],
        )
    finally:
        con.close()
    _invalidate_cache(e)


def list_user_tickers(user_email: str) -> dict[str, dict[str, str]]:
    """Return all custom tickers for a user, grouped by category.

    Shape: {category: {symbol: name}}. Cached in st.session_state to avoid
    hammering the database on every rerun (format_func runs once per option).
    """
    e = _norm(user_email)
    if not e:
        return {}

    # 1. Session-state cache (per user). Hit → no DB call.
    try:
        import streamlit as st  # noqa: PLC0415

        cached = st.session_state.get(_cache_key(e))
        if cached is not None:
            return cached
    except Exception:
        pass

    # 2. Miss → fetch once, store.
    con = _connect()
    try:
        rows = con.execute(
            "SELECT category, symbol, name FROM user_tickers "
            "WHERE user_email = ? ORDER BY category, symbol",
            (e,),
        ).fetchall()
    finally:
        con.close()
    grouped: dict[str, dict[str, str]] = {}
    for cat, sym, name in rows:
        grouped.setdefault(cat, {})[sym] = name or ""

    try:
        import streamlit as st  # noqa: PLC0415

        st.session_state[_cache_key(e)] = grouped
    except Exception:
        pass

    return grouped


def tickers_for_category(user_email: str, category: str) -> dict[str, str]:
    """Just the user's custom tickers within one category: {symbol: name}."""
    return list_user_tickers(user_email).get(category, {})


# ── Combined helpers for views (core + user's custom) ───────────────────────


def combined_map(user_email: str, category: str) -> dict[str, str]:
    """Hardcoded universe tickers merged with the user's custom ones for this category.

    Special case: when category == CUSTOM_CATEGORY ('Custom Ticker'), returns ALL
    of the user's custom tickers across every real category — it's a meta view.

    Returns {symbol: name}, sorted alphabetically by symbol when iterated.
    """
    if category == CUSTOM_CATEGORY:
        result: dict[str, str] = {}
        for _cat, syms in list_user_tickers(user_email).items():
            result.update(syms)
        return dict(sorted(result.items()))
    result = dict(UNIVERSE.get(category, {}))
    result.update(tickers_for_category(user_email, category))
    return dict(sorted(result.items()))


def lookup_name(user_email: str, category: str, ticker: str) -> str:
    """Name for a ticker, checking UNIVERSE first then the user's custom tickers.

    Works across the meta Custom Ticker category too.
    """
    if category == CUSTOM_CATEGORY:
        for _cat, syms in list_user_tickers(user_email).items():
            if ticker in syms:
                return syms[ticker]
        return ""
    name = UNIVERSE.get(category, {}).get(ticker, "")
    if name:
        return name
    return list_user_tickers(user_email).get(category, {}).get(ticker, "")


def combined_symbols(user_email: str, category: str) -> list[str]:
    return list(combined_map(user_email, category).keys())


def combined_label(user_email: str, category: str, symbol: str) -> str:
    if symbol == OTHER:
        from pytalk.i18n import other_label  # noqa: PLC0415 — lazy to avoid cycles

        return other_label()
    name = combined_map(user_email, category).get(symbol, "")
    return f"{symbol} — {name}" if name else symbol
