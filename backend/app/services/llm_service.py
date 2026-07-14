"""
Provider-agnostic LLM interface.

Routes ``generate`` and ``stream_generate`` to OpenRouter, OpenAI, or Gemini
based on ``settings.LLM_PROVIDER`` (default: "openrouter").

Each function has the same signature as its ``gemini_service`` counterpart so
callers swap one import line and get the new provider.
"""

import json
import time
from typing import Any, Generator, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("llm_service")


class LLMError(Exception):
    """Raised when the LLM API call fails."""


# ---------------------------------------------------------------------------
# Provider helpers
# ---------------------------------------------------------------------------


def _provider_config() -> tuple[str, str, str]:
    """Return (base_url, api_key, default_model) for the active provider."""
    match settings.LLM_PROVIDER:
        case "openai":
            return "https://api.openai.com/v1", settings.OPENAI_API_KEY, settings.OPENAI_MODEL
        case "gemini":
            return "", "", settings.GEMINI_MODEL  # gemini handled separately
        case "xai":
            return "https://api.x.ai/v1", settings.XAI_API_KEY, settings.XAI_MODEL
        case "groq":
            return "https://api.groq.com/openai/v1", settings.GROQ_API_KEY, settings.GROQ_MODEL
        case _:  # openrouter
            return "https://openrouter.ai/api/v1", settings.OPENROUTER_API_KEY, settings.LLM_MODEL


def _openai_chat(
    *,
    messages: list[dict[str, str]],
    model: str,
    base_url: str,
    api_key: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
    stream: bool = False,
) -> httpx.Response:
    """Raw POST to an OpenAI-compatible chat completions endpoint."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    with httpx.Client(timeout=timeout) as client:
        return client.post(f"{base_url}/chat/completions", headers=headers, json=body)


# ---------------------------------------------------------------------------
# Non-streaming generation
# ---------------------------------------------------------------------------


def generate(
    *,
    prompt: str,
    system_instruction: str,
    model_name: Optional[str] = None,
    max_output_tokens: int = 1024,
    timeout_seconds: int = 30,
) -> dict:
    """Call the configured LLM provider.

    Returns dict with keys: text, prompt_tokens, completion_tokens, total_tokens, latency_ms.

    Raises LLMError on API errors.
    """
    if settings.LLM_PROVIDER == "gemini":
        from app.services.gemini_service import generate as _gemini_gen  # noqa: PLC0415

        return _gemini_gen(
            prompt=prompt,
            system_instruction=system_instruction,
            model_name=model_name or settings.GEMINI_MODEL,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )

    base_url, api_key, default_model = _provider_config()
    if settings.LLM_PROVIDER == "gemini":
        model = model_name or default_model
    else:
        model = default_model
    if not api_key:
        raise LLMError(f"{settings.LLM_PROVIDER.upper()}_API_KEY is not configured")

    start = time.time()

    try:
        resp = _openai_chat(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_output_tokens,
            temperature=0.0,
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        logger.error(
            "llm.api_error",
            provider=settings.LLM_PROVIDER,
            model=model,
            error=str(exc)[:300],
            latency_ms=round(elapsed, 2),
        )
        raise LLMError(f"LLM API call failed: {exc}") from exc

    elapsed = (time.time() - start) * 1000
    choice = data["choices"][0]
    text = (choice["message"].get("content") or "").strip()
    usage = data.get("usage", {})
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)

    logger.info(
        "llm.generated",
        provider=settings.LLM_PROVIDER,
        model=model,
        prompt_tokens=pt,
        completion_tokens=ct,
        latency_ms=round(elapsed, 2),
    )

    return {
        "text": text,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
        "latency_ms": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# Streaming generation
# ---------------------------------------------------------------------------


def stream_generate(
    *,
    prompt: str,
    system_instruction: str,
    conversation_history: Optional[list[dict[str, str]]] = None,
    model_name: Optional[str] = None,
    max_output_tokens: int = 1024,
    timeout_seconds: int = 30,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    """Stream a response token-by-token from the configured LLM provider.

    Yields ``{"type": "token", "content": str}`` dicts.

    Returns dict with keys: text, prompt_tokens, completion_tokens, total_tokens, latency_ms.

    Raises LLMError on API errors.
    """
    if settings.LLM_PROVIDER == "gemini":
        from app.services.gemini_service import stream_generate as _gemini_fn  # noqa: PLC0415

        yield from _gemini_fn(
            prompt=prompt,
            system_instruction=system_instruction,
            conversation_history=conversation_history,
            model_name=model_name or settings.GEMINI_MODEL,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        return  # pyright: ignore[reportReturnType]

    base_url, api_key, default_model = _provider_config()
    if settings.LLM_PROVIDER == "gemini":
        model = model_name or default_model
    else:
        model = default_model
    if not api_key:
        raise LLMError(f"{settings.LLM_PROVIDER.upper()}_API_KEY is not configured")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_instruction},
    ]
    if conversation_history:
        for msg in conversation_history:
            role = "assistant" if msg["role"] == "assistant" else msg["role"]
            messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    start = time.time()
    full_text = ""

    try:
        resp = _openai_chat(
            messages=messages,
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_output_tokens,
            temperature=0.0,
            timeout=timeout_seconds,
            stream=True,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line or line.startswith(":") or line.strip() == "data: [DONE]":
                continue
            if line.startswith("data: "):
                chunk = json.loads(line[6:])
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    full_text += content
                    yield {"type": "token", "content": content}
    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        logger.error(
            "llm.stream_error",
            provider=settings.LLM_PROVIDER,
            model=model,
            error=str(exc)[:300],
            latency_ms=round(elapsed, 2),
        )
        raise LLMError(f"LLM streaming failed: {exc}") from exc

    elapsed = (time.time() - start) * 1000

    logger.info(
        "llm.stream_complete",
        provider=settings.LLM_PROVIDER,
        model=model,
        latency_ms=round(elapsed, 2),
    )

    # ponytail: OpenAI streaming doesn't report per-chunk token counts.
    return {
        "text": full_text,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "latency_ms": round(elapsed, 2),
    }
