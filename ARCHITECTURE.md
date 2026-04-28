# PyTalk — architecture & maintenance notes

A small reference for the cross-cutting design choices that aren't obvious from
reading any single file. If something here drifts from reality, fix the doc.

---

## What this is

A family-only Streamlit app for analyzing tickers and portfolios:

- **Analysis** — chart a ticker or a portfolio, show past performance, P&L, LLM commentary
- **Portfolios** — create/edit shares-based portfolios, persisted to Turso (cloud) or DuckDB (local)
- **Custom Tickers** — search Yahoo Finance, save tickers outside the built-in universe
- **Screener** — filter the universe by past performance and indicators
- **Learning** — static educational content about strategies and indicators
- **Info / Logout** — session info and sign-out

Auth is OIDC against Microsoft consumer accounts (Hotmail/Outlook). An email
allowlist in `secrets.toml` restricts who can actually use the app once
authenticated.

---

## Stack

| Layer            | Choice                                              |
| ---------------- | --------------------------------------------------- |
| UI framework     | Streamlit ≥ 1.42 (uses native multi-page nav + auth)|
| Charting         | Plotly                                              |
| Data source      | yfinance (Yahoo Finance unofficial)                 |
| LLM (optional)   | Groq via `pytalk.llm`                               |
| Persistence      | Turso (libSQL HTTP) → DuckDB local fallback         |
| Auth             | Streamlit native OIDC → Microsoft consumer endpoint |
| i18n             | In-Python dict (FR + EN) in `pytalk.i18n`           |
| Build/deps       | uv + hatchling, editable install of `src/pytalk`    |

---

## Streamlit execution model — the gotchas that bite

Read this section first if anything in the app looks weird.

### 1. The script runs top-to-bottom on every interaction

Click a checkbox → Streamlit re-runs the entire `App.py` (and the active view)
from line 1. This means:

- Variables don't survive interactions. Use **`st.session_state`** for anything
  that needs to persist across reruns.
- Heavy computations run again every time. Use **`@st.cache_data`** on any
  function that fetches/computes the same thing twice (price loading, currency
  detection, etc.).
- The order of widget calls determines the visual order.

### 2. `st.set_page_config` must be the first Streamlit call

Lives at the top of `App.py`. Don't move it.

### 3. `st.stop()` halts the current script run

Used by the auth gate in `App.py` and "no portfolio selected" guards in views.
Anything below the `st.stop()` doesn't render.

### 4. Widgets need stable `key=` to preserve state across reruns

Every widget that holds user input has an explicit `key=`. Without it,
Streamlit identifies widgets by position, which breaks when the view contains
conditional rendering (e.g., the strategy-specific sliders we used to have).

### 5. Cross-page widget preservation

Streamlit garbage-collects `session_state` keys for widgets that aren't
rendered on the current page. The loop near the top of `App.py` writes every
non-button key back to itself on every render — that bumps the GC clock so a
widget on the Analysis page keeps its value while you're on the Info page.

### 6. File-watcher reload doesn't see `pytalk/` changes

The dev server watches files reachable from the script (App.py + views/).
Edits to `src/pytalk/*.py` (i18n, portfolios, etc.) require a **full process
restart** — Ctrl+C then `streamlit run App.py`. The "Rerun" button isn't
enough; it re-runs the script but reuses already-imported modules.

### 7. Mobile auto-stacking of `st.columns`

Streamlit auto-stacks columns to one-per-row on narrow viewports (~640px and
below). There's no Python-side toggle; you either accept it, chunk into fewer
columns per row in Python, or inject CSS. The Past Performance grid in
`views/analysis.py` accepts the stacking and uses a single `st.columns(N)`
that becomes 1-per-row on phones.

---

## Auth and user scoping

### Login flow (`App.py`)

1. `st.user.is_logged_in` — Streamlit native OIDC check. Requires the `[auth]`
   section in `.streamlit/secrets.toml`.
2. Email is taken from `st.user.email or st.user.preferred_username` (Microsoft
   sometimes only sends one of the two), normalized to lowercase + stripped.
3. **Allowlist gate** — `[access].allowed_emails` in `secrets.toml`. Anyone
   else is shown an "access denied" screen with a sign-out button.
4. **Cross-user session clear** — if a different user signs in via the same
   browser, all `session_state` keys are wiped before continuing. Prevents
   the previous user's portfolio edits / validations / form state from
   leaking visually.

### Per-user data isolation (in the database)

Every user-data table has `user_email` in the primary key:

- `portfolios (user_email, name)`
- `portfolio_holdings (user_email, portfolio_name, ticker)`
- `user_tickers (user_email, category, symbol)`

Every query filters by `user_email`. The view layer always passes the current
user (`CURRENT_USER`) to the storage functions.

If you need to cross-check this on a real DB, run:

```bash
uv run python -c "
from pytalk._storage import connect
con = connect()
print(con.execute('SELECT user_email, COUNT(*) FROM user_tickers GROUP BY user_email').fetchall())
print(con.execute('SELECT user_email, COUNT(*) FROM portfolios GROUP BY user_email').fetchall())
"
```

---

## Persistence layer (`pytalk/_storage.py`)

### Turso first, DuckDB fallback

`use_turso()` returns `True` when both `[turso].url` and `[turso].auth_token`
are set in `secrets.toml`. Otherwise the app falls back to a local
`pytalk.duckdb` file (path comes from `pytalk.data.DB_PATH`).

The Turso client speaks Hrana v2 over HTTP — there's no persistent connection,
each `execute()` is a separate POST. That has performance implications:

### Schema cache (process-level, not per-connection)

`portfolios.py` and `custom_tickers.py` each have a module-level
`_SCHEMA_READY = False`. The first call to `_connect()` runs `CREATE TABLE
IF NOT EXISTS` and probes for new columns; subsequent calls skip those.

This matters because every DDL statement is one HTTP roundtrip on Turso. With
N portfolios on the page, the old behavior was 6N+ roundtrips; now it's 2N+
on the cold first render and ~2N on every rerun.

### Batched fetch for the portfolios page

`get_all_portfolios(user_email)` fetches every portfolio + holdings in 2
queries (one for portfolio names, one for all holdings ordered by portfolio
name). The single-portfolio `get_portfolio()` still exists for the Analysis
page where only one portfolio is loaded at a time.

### Adding a new column without breaking old DBs

`_ensure_holdings_columns()` in `pytalk/portfolios.py` shows the pattern: try
`SELECT col FROM table LIMIT 1`, catch the error, then `ALTER TABLE ADD
COLUMN`. SQLite/libSQL doesn't support `ADD COLUMN IF NOT EXISTS`, hence the
probe.

---

## i18n pattern (`pytalk/i18n.py`)

### One dict, two languages

`TRANSLATIONS["some.key"] = {"en": "...", "fr": "..."}`. Default is French
(`DEFAULT_LANG = "fr"`). Lookup falls back to English, then to the raw key
itself, so a typo never crashes the app — it just shows `some.key` as the
label.

### Adding a translation

1. Add the entry to `TRANSLATIONS` in `pytalk/i18n.py`. Keep the key namespaced
   (`common.*`, `analysis.*`, `portfolios.*`, etc.).
2. Use it in a view: `st.checkbox(t("common.show_legend"), ...)`.
3. **Restart Streamlit** — see "File-watcher reload" gotcha above. Editing
   i18n.py without a restart leaves the old dict in memory; the new key won't
   resolve and you'll see the raw key text.

### Format strings

`t("auth.denied", email=user_email)` — translations can use `{name}`-style
placeholders applied via `str.format`.

---

## Page structure

Multi-page app via `st.navigation` in `App.py`:

```
App.py                    — entry point, auth, session-state lifecycle, nav
views/brand.py            — landing page
views/analysis.py         — single-ticker / portfolio analysis
views/portfolios.py       — CRUD on portfolios
views/custom_tickers.py   — Yahoo search + per-user ticker management
views/screener.py         — universe filtering
views/learning.py         — static educational content (FR/EN)
views/info.py             — session info
views/logout.py           — sign-out confirmation
```

Each view file is its own Streamlit script — Streamlit reruns it from the top
on every interaction. Helpers shared across views go in `pytalk/`.

---

## Domain layer (`src/pytalk/`)

| Module             | Responsibility                                          |
| ------------------ | ------------------------------------------------------- |
| `data.py`          | yfinance wrapper, currency lookup, category detection   |
| `indicators.py`    | RSI, SMA, EMA, etc. — pure pandas                       |
| `portfolios.py`    | `Portfolio`/`Holding` dataclasses + CRUD on Turso/DuckDB|
| `custom_tickers.py`| Per-user custom ticker CRUD + merging with `UNIVERSE`   |
| `universe.py`      | Hard-coded ticker categories and labels                 |
| `i18n.py`          | Translation dict + `t(key)` lookup + language selector  |
| `llm.py`           | Groq client wrapper — `ask_llm_stream`, `llm_available` |
| `_storage.py`      | Turso HTTP client + DuckDB fallback                     |

Note: `pytalk.indicators.add_indicators` is exported via `pytalk/__init__.py`
but the app uses the lower-level functions directly (`rsi`, `sma`).

---

## Common edits — how-to

### Add a new translation
See "i18n pattern" above. Restart Streamlit after editing.

### Add a new ticker to the built-in universe
Edit `src/pytalk/universe.py` (`UNIVERSE` dict, keyed by category). Restart.

### Add a new asset category
1. Add the category to `CATEGORIES` and `UNIVERSE` in `pytalk/universe.py`.
2. Add a translation `category.<name>` for the label.
3. The Analysis sidebar picker, Portfolios editor, and Custom Tickers list all
   render `CATEGORIES` automatically.

### Add a new view
1. Create `views/myview.py`. Use `st.title(t("nav.myview"))`, etc.
2. Register it in `App.py`'s `st.navigation([...])` list.
3. Add `nav.myview` translation.
4. If the view uses sidebar widgets, add the page title to
   `_PAGES_WITH_SIDEBAR_WIDGETS` in `App.py` so the brand sidebar image is
   suppressed.

### Add a new persistent column
1. Add to the `CREATE TABLE` in the relevant module's `_SCHEMA_STATEMENTS`.
2. Add an `_ensure_columns` ALTER probe so existing DBs migrate.
3. Update the dataclass + the `INSERT` and `SELECT` queries.
4. Reset `_SCHEMA_READY = False` for one local run if you want to verify the
   migration runs (not strictly necessary — fresh processes always run it once).

---

## Operational notes

### Local dev

```bash
uv sync                       # install deps (or refresh after pyproject changes)
uv run streamlit run App.py
```

Browser opens at http://localhost:8501. Sign in with a Microsoft account that
appears in `[access].allowed_emails`.

### Secrets file

`.streamlit/secrets.toml` — gitignored. Required sections:

- `GROQ_API_KEY` (top-level) — optional, enables LLM commentary
- `[auth]` — Streamlit OIDC config; `redirect_uri`, `cookie_secret`,
  `client_id`, `client_secret`, `server_metadata_url`, `client_kwargs`
- `[access].allowed_emails` — list of permitted user emails
- `[turso]` — `url` and `auth_token`. Omit for local DuckDB.

### Deploy target

Streamlit Community Cloud. The same `secrets.toml` content goes into the
Settings → Secrets tab on the cloud dashboard (the file isn't uploaded; you
paste its contents).

### Tests

Pytest in `tests/`. Currently only covers `pytalk.indicators`. Run:

```bash
uv run --with pytest pytest -q
```
