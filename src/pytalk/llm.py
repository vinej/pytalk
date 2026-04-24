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
