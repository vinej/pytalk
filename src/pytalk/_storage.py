"""Shared storage backend: Turso (cloud) or DuckDB (local fallback).

Used by both portfolios and custom_tickers. Keeps the connection logic in one
place so backend changes (e.g. a future swap to Supabase) only need touching
a single file.
"""
from __future__ import annotations

import os
from typing import Any, Union

import duckdb
import requests

from pytalk.data import DB_PATH


class _TursoResult:
    __slots__ = ("_rows",)

    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None


def _to_arg(v: Any) -> dict:
    # Turso Hrana v2 protocol: integer = stringified, float = JSON number, text = string.
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def _parse_cell(cell: dict) -> Any:
    t = cell.get("type")
    if t == "null":
        return None
    v = cell.get("value")
    if t == "integer":
        return int(v) if v is not None else None
    if t == "float":
        return float(v) if v is not None else None
    return v


class TursoConn:
    """Minimal Turso HTTP client (v2/pipeline). Writes in execute_many are atomic."""

    def __init__(self, url: str, token: str):
        host = url.strip()
        if host.startswith("libsql://"):
            host = "https://" + host[len("libsql://") :]
        elif not host.startswith("http"):
            host = "https://" + host
        self._endpoint = host.rstrip("/") + "/v2/pipeline"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _post(self, reqs: list[dict]) -> dict:
        r = requests.post(
            self._endpoint,
            json={"requests": reqs + [{"type": "close"}]},
            headers=self._headers,
            timeout=30,
        )
        # Include body in 4xx/5xx errors — Turso's detail lives in the response text.
        if r.status_code >= 400:
            raise RuntimeError(
                f"Turso HTTP {r.status_code}: {r.text[:800]}"
            )
        data = r.json()
        for idx, res in enumerate(data.get("results", [])):
            if res.get("type") == "error":
                err = res.get("error") or {}
                raise RuntimeError(
                    f"Turso error on statement {idx}: {err.get('message', err)}"
                )
        return data

    def execute(self, sql: str, params: tuple | list = ()) -> _TursoResult:
        args = [_to_arg(p) for p in params]
        data = self._post([{"type": "execute", "stmt": {"sql": sql, "args": args}}])
        first = data["results"][0]
        result = first.get("response", {}).get("result", {})
        rows_raw = result.get("rows", []) or []
        rows = [tuple(_parse_cell(cell) for cell in row) for row in rows_raw]
        return _TursoResult(rows)

    def execute_many(self, statements: list[tuple[str, tuple]]) -> None:
        reqs = []
        for sql, params in statements:
            args = [_to_arg(p) for p in params]
            reqs.append({"type": "execute", "stmt": {"sql": sql, "args": args}})
        self._post(reqs)

    def close(self) -> None:
        pass  # stateless


def _get_turso_creds() -> tuple[str, str]:
    try:
        import streamlit as st  # noqa: PLC0415

        t = st.secrets.get("turso", {}) or {}
        url = (t.get("url") or "").strip()
        token = (t.get("auth_token") or "").strip()
        if url and token:
            return url, token
    except Exception:
        pass
    return (
        os.environ.get("TURSO_URL", "").strip(),
        os.environ.get("TURSO_AUTH_TOKEN", "").strip(),
    )


def use_turso() -> bool:
    url, token = _get_turso_creds()
    return bool(url and token)


def current_backend_label() -> str:
    return "Turso (cloud)" if use_turso() else "DuckDB (local)"


def connect() -> Union[TursoConn, "duckdb.DuckDBPyConnection"]:
    """Return a connection to whichever backend is active."""
    if use_turso():
        url, token = _get_turso_creds()
        return TursoConn(url, token)
    return duckdb.connect(str(DB_PATH))


def ensure_schema(con: Any, statements: list[str]) -> None:
    for stmt in statements:
        con.execute(stmt)


def write_tx(con: Any, statements: list[tuple[str, tuple]]) -> None:
    """Atomic write for either backend."""
    if isinstance(con, TursoConn):
        con.execute_many(statements)
        return
    con.execute("BEGIN")
    try:
        for sql, params in statements:
            con.execute(sql, list(params))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
