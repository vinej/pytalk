"""Portfolio storage — uses pytalk._storage (Turso cloud or DuckDB local)."""
from __future__ import annotations

from dataclasses import dataclass

from pytalk._storage import connect, current_backend_label, ensure_schema, write_tx


@dataclass
class Holding:
    ticker: str
    category: str
    weight: float = 1.0


@dataclass
class Portfolio:
    name: str
    holdings: list[Holding]

    def normalized_weights(self) -> dict[str, float]:
        total = sum(h.weight for h in self.holdings)
        if total <= 0:
            raise ValueError("Portfolio weights must sum to a positive value")
        return {h.ticker: h.weight / total for h in self.holdings}


_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS portfolios (
        user_email TEXT NOT NULL,
        name       TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_email, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_holdings (
        user_email     TEXT NOT NULL,
        portfolio_name TEXT NOT NULL,
        ticker         TEXT NOT NULL,
        category       TEXT NOT NULL,
        weight         REAL NOT NULL DEFAULT 1.0,
        PRIMARY KEY (user_email, portfolio_name, ticker)
    )
    """,
]


def _connect():
    con = connect()
    ensure_schema(con, _SCHEMA_STATEMENTS)
    return con


def current_db_label() -> str:
    return current_backend_label()


def _require_email(user_email: str) -> str:
    e = (user_email or "").strip().lower()
    if not e:
        raise ValueError("User email is required for portfolio access")
    return e


def list_portfolios(user_email: str) -> list[str]:
    e = _require_email(user_email)
    con = _connect()
    try:
        rows = con.execute(
            "SELECT name FROM portfolios WHERE user_email = ? ORDER BY name", (e,)
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def get_portfolio(user_email: str, name: str) -> Portfolio | None:
    e = _require_email(user_email)
    con = _connect()
    try:
        row = con.execute(
            "SELECT name FROM portfolios WHERE user_email = ? AND name = ?",
            (e, name),
        ).fetchone()
        if not row:
            return None
        holdings_rows = con.execute(
            """
            SELECT ticker, category, weight
            FROM portfolio_holdings
            WHERE user_email = ? AND portfolio_name = ?
            ORDER BY ticker
            """,
            (e, name),
        ).fetchall()
        holdings = [
            Holding(ticker=t, category=c, weight=float(w))
            for t, c, w in holdings_rows
        ]
        return Portfolio(name=name, holdings=holdings)
    finally:
        con.close()


def save_portfolio(user_email: str, portfolio: Portfolio) -> None:
    e = _require_email(user_email)
    if not portfolio.name.strip():
        raise ValueError("Portfolio name is required")
    if not portfolio.holdings:
        raise ValueError("Portfolio must have at least one holding")
    con = _connect()
    try:
        stmts: list[tuple[str, tuple]] = [
            (
                "INSERT INTO portfolios (user_email, name) VALUES (?, ?) "
                "ON CONFLICT (user_email, name) DO NOTHING",
                (e, portfolio.name),
            ),
            (
                "DELETE FROM portfolio_holdings "
                "WHERE user_email = ? AND portfolio_name = ?",
                (e, portfolio.name),
            ),
        ]
        for h in portfolio.holdings:
            stmts.append(
                (
                    """
                    INSERT INTO portfolio_holdings
                        (user_email, portfolio_name, ticker, category, weight)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (e, portfolio.name, h.ticker.upper(), h.category, float(h.weight)),
                )
            )
        write_tx(con, stmts)
    finally:
        con.close()


def delete_portfolio(user_email: str, name: str) -> None:
    e = _require_email(user_email)
    con = _connect()
    try:
        write_tx(
            con,
            [
                (
                    "DELETE FROM portfolio_holdings "
                    "WHERE user_email = ? AND portfolio_name = ?",
                    (e, name),
                ),
                (
                    "DELETE FROM portfolios WHERE user_email = ? AND name = ?",
                    (e, name),
                ),
            ],
        )
    finally:
        con.close()
