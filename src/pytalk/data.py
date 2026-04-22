from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).resolve().parents[2] / "data"
CACHE_DIR.mkdir(exist_ok=True)
DB_PATH = CACHE_DIR / "prices.duckdb"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ticker   VARCHAR NOT NULL,
    date     DATE    NOT NULL,
    open     DOUBLE,
    high     DOUBLE,
    low      DOUBLE,
    close    DOUBLE,
    volume   BIGINT,
    PRIMARY KEY (ticker, date)
);
"""


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH))
    con.execute(_SCHEMA)
    return con


def _download(ticker: str, start: date, end: date) -> pd.DataFrame:
    # Yahoo's "Close" is already split-adjusted by default; auto_adjust=False keeps
    # it split-adjusted but NOT dividend-adjusted = price return, which is what we want.
    t = yf.Ticker(ticker)
    try:
        hist = t.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            actions=False,
        )
    except Exception:
        return pd.DataFrame()

    if hist.empty:
        return pd.DataFrame()

    hist = hist.reset_index()
    hist.columns = [str(c).lower() for c in hist.columns]

    date_col = "date" if "date" in hist.columns else "datetime"
    dt = pd.to_datetime(hist[date_col])
    if getattr(dt.dt, "tz", None) is not None:
        dt = dt.dt.tz_localize(None)
    hist["date"] = dt.dt.date

    return hist[["date", "open", "high", "low", "close", "volume"]]


def get_currency(ticker: str) -> str:
    """Return the 3-letter currency code reported by Yahoo (e.g. 'USD', 'CAD'), or '' if unknown."""
    try:
        info = yf.Ticker(ticker).info
        return (info.get("currency") or "").upper()
    except Exception:
        return ""


def get_prices(ticker: str, start: date, end: date, *, use_cache: bool = True) -> pd.DataFrame:
    """Return OHLCV for ticker in [start, end], fetching and caching missing days."""
    ticker = ticker.upper()
    con = _connect()
    try:
        if use_cache:
            cached = con.execute(
                "SELECT date FROM prices WHERE ticker = ? AND date BETWEEN ? AND ?",
                [ticker, start, end],
            ).df()
            have = set(cached["date"].tolist()) if not cached.empty else set()
        else:
            have = set()

        expected_days = pd.bdate_range(start, end).date
        missing = [d for d in expected_days if d not in have]

        if missing:
            fresh = _download(ticker, min(missing), max(missing))
            if not fresh.empty:
                fresh.insert(0, "ticker", ticker)
                con.execute("INSERT OR REPLACE INTO prices SELECT * FROM fresh")

        out = con.execute(
            """
            SELECT date, open, high, low, close, volume
            FROM prices
            WHERE ticker = ? AND date BETWEEN ? AND ?
            ORDER BY date
            """,
            [ticker, start, end],
        ).df()
        out["date"] = pd.to_datetime(out["date"])
        return out.set_index("date")
    finally:
        con.close()
