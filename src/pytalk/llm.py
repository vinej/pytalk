"""LLM helper that routes to Groq (cloud) if GROQ_API_KEY is set, else local Ollama.

Usage is provider-agnostic: call ask_llm_stream(prompt) / llm_available().
Old names (ask_ollama_stream, ollama_available) are kept as aliases for back-compat.
"""
from __future__ import annotations

import json
import os
from typing import Iterator

import requests

# Endpoints
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Default models per provider
DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a concise financial analysis assistant helping a retail investor.

Rules:
- Describe what the data shows; never invent numbers that aren't in the prompt.
- Flag risks honestly: drawdowns, overfitting, small sample sizes, survivor bias.
- When the user's question lists numbered points, respond as a matching numbered
  list (markdown "1. ... 2. ..."), one short sentence per point. Do not merge
  points into a single paragraph.
- Never give buy/sell advice; frame observations as "what this suggests", not "what to do".
- If you don't have the data to answer, say so rather than guessing.
"""

_LANGUAGE_DIRECTIVES = {
    "fr": "Respond in French (français). Keep ticker symbols and numeric values unchanged.",
    "en": "Respond in English.",
}


def _active_language_directive() -> str:
    """Read the current UI language from Streamlit session state, if any."""
    try:
        import streamlit as st

        lang = st.session_state.get("lang")
    except Exception:
        return ""
    return _LANGUAGE_DIRECTIVES.get(lang, "")


def _get_groq_key() -> str | None:
    """Look up GROQ_API_KEY from env vars or Streamlit secrets."""
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        import streamlit as st

        return st.secrets.get("GROQ_API_KEY")  # type: ignore[attr-defined]
    except Exception:
        return None


def active_provider() -> str:
    """'groq' if API key is configured, else 'ollama'."""
    return "groq" if _get_groq_key() else "ollama"


def llm_available() -> bool:
    """Check whether the currently-active provider is reachable."""
    if active_provider() == "groq":
        return _get_groq_key() is not None
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def current_model_label() -> str:
    """Short label of the active provider + model, for display (e.g. sidebar header)."""
    if active_provider() == "groq":
        return f"{DEFAULT_GROQ_MODEL} (Groq)"
    return f"{DEFAULT_OLLAMA_MODEL} (local Ollama)"


def unavailable_message() -> str:
    """Human-readable hint when the LLM can't be used."""
    if active_provider() == "groq":
        return "Groq API key is set but the service couldn't be reached."
    return (
        "No LLM provider configured. Either:\n"
        "  • Run Ollama locally: `ollama serve` then `ollama pull qwen3:8b`, or\n"
        "  • Set `GROQ_API_KEY` (env var or Streamlit secret) for cloud inference."
    )


# ── Ollama streaming ────────────────────────────────────────────────────────
def _ollama_stream(
    prompt: str, system: str | None, model: str, timeout: int
) -> Iterator[str]:
    payload = {"model": model, "prompt": prompt, "stream": True}
    if system:
        payload["system"] = system
    with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if chunk.get("response"):
                yield chunk["response"]
            if chunk.get("done"):
                break


# ── Groq streaming (OpenAI-compatible SSE) ──────────────────────────────────
def _groq_stream(
    prompt: str, system: str | None, model: str, timeout: int
) -> Iterator[str]:
    api_key = _get_groq_key()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not configured")
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages, "stream": True}
    with requests.post(
        GROQ_URL, json=payload, headers=headers, stream=True, timeout=timeout
    ) as r:
        r.raise_for_status()
        r.encoding = "utf-8"  # Groq sometimes omits charset; force UTF-8
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                yield content


# ── Public API ──────────────────────────────────────────────────────────────
def ask_llm_stream(
    prompt: str,
    *,
    system: str | None = SYSTEM_PROMPT,
    model: str | None = None,
    timeout: int = 180,
) -> Iterator[str]:
    """Stream an LLM completion using the active provider."""
    directive = _active_language_directive()
    if directive and system is not None:
        system = f"{system}\n\n{directive}"
    if active_provider() == "groq":
        yield from _groq_stream(prompt, system, model or DEFAULT_GROQ_MODEL, timeout)
    else:
        yield from _ollama_stream(
            prompt, system, model or DEFAULT_OLLAMA_MODEL, timeout
        )


def ask_llm(
    prompt: str,
    *,
    system: str | None = SYSTEM_PROMPT,
    model: str | None = None,
    timeout: int = 180,
) -> str:
    """Blocking LLM call — collects the streamed response into one string."""
    return "".join(
        ask_llm_stream(prompt, system=system, model=model, timeout=timeout)
    )


# Backwards-compat aliases so existing view code keeps working.
ask_ollama_stream = ask_llm_stream
ask_ollama = ask_llm
ollama_available = llm_available


# ── Prompt builders ─────────────────────────────────────────────────────────
# Centralizing prompt text here keeps wording consistent across views and
# makes the templates testable in isolation. The LLM language is set via
# `_active_language_directive()` on top of SYSTEM_PROMPT — prompt bodies stay
# in English regardless of UI language.


def build_validate_portfolio_prompt(
    *,
    name: str,
    holdings,
    weights: dict[str, float],
) -> str:
    """Build the standard "review this portfolio structure" prompt.

    `holdings` is any iterable of objects with `.ticker` and `.category`.
    `weights` maps ticker → fractional weight (caller decides whether weights
    come from declared targets or from current dollar values).
    """
    from pytalk.universe import UNIVERSE  # local — avoid circular at import time

    holdings_list = list(holdings)
    by_type: dict[str, float] = {}
    for h in holdings_list:
        by_type[h.category] = by_type.get(h.category, 0.0) + weights[h.ticker]
    mix_text = ", ".join(f"{cat}: {w:.1%}" for cat, w in by_type.items())
    holdings_text = "\n".join(
        f"  - {h.ticker} ({h.category}) "
        f"[{UNIVERSE.get(h.category, {}).get(h.ticker) or 'custom'}] — "
        f"{weights[h.ticker]:.1%}"
        for h in holdings_list
    )
    return f"""Review this portfolio structure.

Name: {name}
Total holdings: {len(holdings_list)}
Asset-type mix: {mix_text}

Holdings:
{holdings_text}

Respond as a markdown numbered list — one short sentence per point, no introduction, no final paragraph:
1. Overall diversification — across asset classes, geography, and sectors.
2. Concentration risks — any single holding or type too dominant?
3. Overlap — do multiple holdings track the same thing (e.g. two S&P 500 ETFs)?
4. What kind of investor this portfolio suits (growth / income / capital preservation).
5. One honest caveat (hidden correlations, home-bias, missing asset classes, etc.).
6. One constructive observation — what would make it more robust, without recommending specific tickers.

Don't invent facts about any holding you don't recognise; just say "unfamiliar".
"""


def build_describe_ticker_prompt(
    *,
    ticker: str,
    name: str,
    perf_prices,
    currency: str,
    end,
) -> str:
    """Build the standard "describe this ticker" prompt.

    Computes a small bundle of indicators (SMA 20/50/200, RSI 14, 52w
    position, 1y annualized volatility, implied dividend yield from TR-PR
    gap) from `perf_prices` (a DataFrame with `close` + `adj_close`) and
    embeds the snapshot into the prompt body.
    """
    import pandas as pd  # local — keep llm.py importable without pandas install

    from pytalk.indicators import rsi

    close = perf_prices["close"]
    adj = perf_prices["adj_close"]
    curr = float(close.iloc[-1])

    def _last(s) -> float | None:
        v = s.dropna()
        return float(v.iloc[-1]) if not v.empty else None

    sma20 = _last(close.rolling(20).mean())
    sma50 = _last(close.rolling(50).mean())
    sma200 = _last(close.rolling(200).mean())
    rsi14 = _last(rsi(close, 14))

    year_close = close.loc[pd.Timestamp(end) - pd.DateOffset(months=12) :]
    pos_52w: float | None = None
    vol: float | None = None
    if not year_close.empty and year_close.max() > year_close.min():
        pos_52w = (
            (curr - float(year_close.min()))
            / (float(year_close.max()) - float(year_close.min()))
            * 100
        )
    year_rets = year_close.pct_change().dropna()
    if len(year_rets) > 20:
        vol = float(year_rets.std()) * (252 ** 0.5) * 100

    # 1y TR vs PR → implied dividend yield
    target_1y = pd.Timestamp(end) - pd.DateOffset(months=12)
    before_1y = perf_prices.loc[:target_1y]
    div_text = "n/a"
    if not before_1y.empty:
        past_pr = float(before_1y["close"].iloc[-1])
        past_tr = float(before_1y["adj_close"].iloc[-1])
        if past_pr > 0 and past_tr > 0:
            pr_1y = (curr / past_pr - 1) * 100
            tr_1y = (float(adj.iloc[-1]) / past_tr - 1) * 100
            gap = tr_1y - pr_1y
            if gap > 0.5:
                div_text = f"~{gap:.1f}% (meaningful dividend contribution)"
            elif gap > 0.05:
                div_text = f"~{gap:.2f}% (small dividend)"
            else:
                div_text = "negligible / no dividend"

    def _fmt(v: float | None, suffix: str = "") -> str:
        return "—" if v is None else f"{v:.2f}{suffix}"

    name_bit = f" ({name})" if name else ""
    return f"""Summarize the current technical state of {ticker}{name_bit}.

Current price: {curr:.2f} {currency or ''}
Moving averages:
  SMA 20:  {_fmt(sma20)}
  SMA 50:  {_fmt(sma50)}
  SMA 200: {_fmt(sma200)}
Momentum:
  RSI(14): {_fmt(rsi14)}
Range:
  52-week position: {_fmt(pos_52w, '%')} (0 = at 52w low, 100 = at 52w high)
Risk:
  Annualized volatility (1y): {_fmt(vol, '%')}
Dividend character:
  1y TR-PR gap: {div_text}

Respond as a markdown numbered list - one short sentence per point, no introduction, no final paragraph:
1. Trend — where the price sits vs SMA 50 and SMA 200, what that suggests.
2. Momentum — what RSI(14) and recent moves imply (overbought / neutral / oversold).
3. Volatility regime — calm, elevated, or extreme compared to normal equity (~15-20%).
4. Range position — near 52-week high, middle, or near 52-week low.
5. Dividend character — is this a meaningful income payer?
6. Honest caveat — what this snapshot does NOT tell you (company fundamentals, earnings, macro, valuation, current news).
"""
