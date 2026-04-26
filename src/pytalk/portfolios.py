"""Portfolio storage — uses pytalk._storage (Turso cloud or DuckDB local)."""
from __future__ import annotations

from dataclasses import dataclass

from pytalk._storage import connect, current_backend_label, ensure_schema, write_tx


@dataclass
class Holding:
    ticker: str
    category: str
    weight: float = 1.0
    shares: float = 0.0
    buy_date: str | None = None  # ISO yyyy-mm-dd, or None for legacy holdings

    @property
    def has_position(self) -> bool:
        """True when this holding has shares + buy_date set (not a legacy weight-only row)."""
        return self.shares > 0 and bool(self.buy_date)


@dataclass
class Portfolio:
    name: str
    holdings: list[Holding]

    def normalized_weights(self) -> dict[str, float]:
        total = sum(h.weight for h in self.holdings)
        if total <= 0:
            raise ValueError("Portfolio weights must sum to a positive value")
        return {h.ticker: h.weight / total for h in self.holdings}

    def has_positions(self) -> bool:
        """True iff every holding has shares + buy_date set."""
        return bool(self.holdings) and all(h.has_position for h in self.holdings)

    def weights_from_values(self, values: dict[str, float]) -> dict[str, float]:
        """Compute fractional weights from current dollar values per ticker."""
        total = sum(values.get(h.ticker, 0.0) for h in self.holdings)
        if total <= 0:
            raise ValueError("Total portfolio value must be positive")
        return {h.ticker: values.get(h.ticker, 0.0) / total for h in self.holdings}


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


def _ensure_holdings_columns(con) -> None:
    """Add shares + buy_date columns to portfolio_holdings if missing.

    SQLite/libSQL does not support `ADD COLUMN IF NOT EXISTS`, so we probe with
    a SELECT and only ALTER when the probe fails.
    """
    for column, ddl in (
        ("shares",   "ALTER TABLE portfolio_holdings ADD COLUMN shares REAL DEFAULT 0"),
        ("buy_date", "ALTER TABLE portfolio_holdings ADD COLUMN buy_date TEXT"),
    ):
        try:
            con.execute(f"SELECT {column} FROM portfolio_holdings LIMIT 1")
        except Exception:
            try:
                con.execute(ddl)
            except Exception:
                pass  # raced or already added


_SCHEMA_READY = False


def _connect():
    """Schema/column ensure runs once per process — they're idempotent DDL but
    each call costs an HTTP roundtrip on Turso, which compounds badly when the
    same page renders 4+ portfolios."""
    global _SCHEMA_READY
    con = connect()
    if not _SCHEMA_READY:
        ensure_schema(con, _SCHEMA_STATEMENTS)
        _ensure_holdings_columns(con)
        _SCHEMA_READY = True
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


def get_all_portfolios(user_email: str) -> list[Portfolio]:
    """Fetch every portfolio + all its holdings in 2 queries instead of 1+N.

    The portfolios page renders every portfolio for the user; the per-portfolio
    `get_portfolio` loop was the dominant cost on Turso (HTTP per query).
    """
    e = _require_email(user_email)
    con = _connect()
    try:
        port_rows = con.execute(
            "SELECT name FROM portfolios WHERE user_email = ? ORDER BY name", (e,)
        ).fetchall()
        names = [r[0] for r in port_rows]
        if not names:
            return []
        h_rows = con.execute(
            """
            SELECT portfolio_name, ticker, category, weight, shares, buy_date
            FROM portfolio_holdings
            WHERE user_email = ?
            ORDER BY portfolio_name, ticker
            """,
            (e,),
        ).fetchall()
    finally:
        con.close()

    holdings_by_portfolio: dict[str, list[Holding]] = {n: [] for n in names}
    for pn, tk, cat, w, sh, bd in h_rows:
        holdings_by_portfolio.setdefault(pn, []).append(
            Holding(
                ticker=tk,
                category=cat,
                weight=float(w or 1.0),
                shares=float(sh or 0.0),
                buy_date=bd or None,
            )
        )
    return [Portfolio(name=n, holdings=holdings_by_portfolio.get(n, [])) for n in names]


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
            SELECT ticker, category, weight, shares, buy_date
            FROM portfolio_holdings
            WHERE user_email = ? AND portfolio_name = ?
            ORDER BY ticker
            """,
            (e, name),
        ).fetchall()
        holdings = [
            Holding(
                ticker=tk,
                category=cat,
                weight=float(w or 1.0),
                shares=float(sh or 0.0),
                buy_date=bd or None,
            )
            for tk, cat, w, sh, bd in holdings_rows
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
                        (user_email, portfolio_name, ticker, category, weight, shares, buy_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        e,
                        portfolio.name,
                        h.ticker.upper(),
                        h.category,
                        float(h.weight),
                        float(h.shares or 0.0),
                        h.buy_date or None,
                    ),
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
