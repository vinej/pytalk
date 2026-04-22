from __future__ import annotations

from dataclasses import dataclass

import duckdb

from pytalk.data import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolios (
    name       VARCHAR PRIMARY KEY,
    created_at TIMESTAMP DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    portfolio_name VARCHAR NOT NULL,
    ticker         VARCHAR NOT NULL,
    category       VARCHAR NOT NULL,
    weight         DOUBLE  NOT NULL DEFAULT 1.0,
    PRIMARY KEY (portfolio_name, ticker)
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
    con.execute(_SCHEMA)
    return con


def list_portfolios() -> list[str]:
    con = _connect()
    try:
        rows = con.execute("SELECT name FROM portfolios ORDER BY name").fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def get_portfolio(name: str) -> Portfolio | None:
    con = _connect()
    try:
        row = con.execute("SELECT name FROM portfolios WHERE name = ?", [name]).fetchone()
        if not row:
            return None
        holdings_rows = con.execute(
            """
            SELECT ticker, category, weight
            FROM portfolio_holdings
            WHERE portfolio_name = ?
            ORDER BY ticker
            """,
            [name],
        ).fetchall()
        holdings = [Holding(ticker=t, category=c, weight=w) for t, c, w in holdings_rows]
        return Portfolio(name=name, holdings=holdings)
    finally:
        con.close()


def save_portfolio(portfolio: Portfolio) -> None:
    if not portfolio.name.strip():
        raise ValueError("Portfolio name is required")
    if not portfolio.holdings:
        raise ValueError("Portfolio must have at least one holding")
    con = _connect()
    try:
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO portfolios (name) VALUES (?) ON CONFLICT (name) DO NOTHING",
            [portfolio.name],
        )
        con.execute(
            "DELETE FROM portfolio_holdings WHERE portfolio_name = ?", [portfolio.name]
        )
        for h in portfolio.holdings:
            con.execute(
                """
                INSERT INTO portfolio_holdings (portfolio_name, ticker, category, weight)
                VALUES (?, ?, ?, ?)
                """,
                [portfolio.name, h.ticker.upper(), h.category, float(h.weight)],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def delete_portfolio(name: str) -> None:
    con = _connect()
    try:
        con.execute("BEGIN")
        con.execute("DELETE FROM portfolio_holdings WHERE portfolio_name = ?", [name])
        con.execute("DELETE FROM portfolios WHERE name = ?", [name])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
