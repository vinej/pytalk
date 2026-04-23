from __future__ import annotations

from dataclasses import dataclass

import duckdb

from pytalk.data import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolios (
    user_email VARCHAR NOT NULL,
    name       VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (user_email, name)
);
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    user_email     VARCHAR NOT NULL,
    portfolio_name VARCHAR NOT NULL,
    ticker         VARCHAR NOT NULL,
    category       VARCHAR NOT NULL,
    weight         DOUBLE  NOT NULL DEFAULT 1.0,
    PRIMARY KEY (user_email, portfolio_name, ticker)
);
"""


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


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH))
    # Migrate old (un-scoped) schema if present
    try:
        cols = {row[0] for row in con.execute("DESCRIBE portfolios").fetchall()}
        if "user_email" not in cols:
            con.execute("DROP TABLE IF EXISTS portfolio_holdings")
            con.execute("DROP TABLE IF EXISTS portfolios")
    except Exception:
        pass  # tables don't exist yet — CREATE TABLE IF NOT EXISTS will handle it
    con.execute(_SCHEMA)
    return con


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
            "SELECT name FROM portfolios WHERE user_email = ? ORDER BY name", [e]
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def get_portfolio(user_email: str, name: str) -> Portfolio | None:
    e = _require_email(user_email)
    con = _connect()
    try:
        row = con.execute(
            "SELECT name FROM portfolios WHERE user_email = ? AND name = ?", [e, name]
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
            [e, name],
        ).fetchall()
        holdings = [Holding(ticker=t, category=c, weight=w) for t, c, w in holdings_rows]
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
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO portfolios (user_email, name) VALUES (?, ?) "
            "ON CONFLICT (user_email, name) DO NOTHING",
            [e, portfolio.name],
        )
        con.execute(
            "DELETE FROM portfolio_holdings "
            "WHERE user_email = ? AND portfolio_name = ?",
            [e, portfolio.name],
        )
        for h in portfolio.holdings:
            con.execute(
                """
                INSERT INTO portfolio_holdings
                    (user_email, portfolio_name, ticker, category, weight)
                VALUES (?, ?, ?, ?, ?)
                """,
                [e, portfolio.name, h.ticker.upper(), h.category, float(h.weight)],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def delete_portfolio(user_email: str, name: str) -> None:
    e = _require_email(user_email)
    con = _connect()
    try:
        con.execute("BEGIN")
        con.execute(
            "DELETE FROM portfolio_holdings "
            "WHERE user_email = ? AND portfolio_name = ?",
            [e, name],
        )
        con.execute(
            "DELETE FROM portfolios WHERE user_email = ? AND name = ?", [e, name]
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
