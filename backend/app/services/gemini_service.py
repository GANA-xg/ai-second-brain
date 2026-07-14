"""
Minimal Gemini API integration.

Responsibilities:
- Configure the client with the API key
- Call Gemini with a full prompt (system instruction + user content)
- Return the response text and token usage
- Support streaming generation for SSE chat

No retrieval logic, no prompt construction, no RAG orchestration.
"""

import json
import time
from typing import Any, Generator, Optional

import google.generativeai as genai

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("gemini_service")


# ---------------------------------------------------------------------------
# Lazy singleton for the generative model
# ---------------------------------------------------------------------------

_model_instance = None
_model_name_loaded: Optional[str] = None


def _get_model(model_name: str):
    """Get or create a cached GenerativeModel instance."""
    global _model_instance, _model_name_loaded
    if _model_instance is not None and _model_name_loaded == model_name:
        return _model_instance

    genai.configure(api_key=settings.GEMINI_API_KEY)
    _model_instance = genai.GenerativeModel(model_name=model_name)
    _model_name_loaded = model_name
    return _model_instance


class GeminiServiceError(Exception):
    """Raised when the Gemini API call fails."""


def generate(
    *,
    prompt: str,
    system_instruction: str,
    model_name: str = settings.GEMINI_MODEL,
    max_output_tokens: int = settings.MAX_RESPONSE_TOKENS,
    timeout_seconds: int = 30,
) -> dict:
    """Call Gemini with a system instruction and user prompt.

    Args:
        prompt: The user message / assembled RAG prompt.
        system_instruction: The system prompt with behavioural rules.
        model_name: Gemini model identifier.
        max_output_tokens: Max tokens in the response.
        timeout_seconds: Timeout for the API call.

    Returns:
        Dict with keys: text, prompt_tokens, completion_tokens, total_tokens, latency_ms.

    Raises:
        GeminiServiceError: On API errors or timeouts.
    """
    if not settings.GEMINI_API_KEY:
        raise GeminiServiceError("GEMINI_API_KEY is not configured")

    model = _get_model(model_name)

    start = time.time()

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_output_tokens,
                temperature=0.0,  # deterministic for grounded answers
                top_p=0.95,
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
            request_options={"timeout": timeout_seconds * 1000},
        )
    except Exception as exc:
        elapsed_ms = (time.time() - start) * 1000
        logger.error(
            "gemini.api_error",
            model=model_name,
            error=str(exc)[:300],
            latency_ms=round(elapsed_ms, 2),
        )
        raise GeminiServiceError(
            f"Gemini API call failed: {exc}"
        ) from exc

    elapsed_ms = (time.time() - start) * 1000

    # Extract token usage if available
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    try:
        if response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count or 0
            completion_tokens = response.usage_metadata.candidates_token_count or 0
            total_tokens = response.usage_metadata.total_token_count or 0
    except Exception:
        pass

    text = response.text if hasattr(response, "text") else ""

    logger.info(
        "gemini.generated",
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=round(elapsed_ms, 2),
    )

    return {
        "text": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": round(elapsed_ms, 2),
    }


# ---------------------------------------------------------------------------
# Streaming generation
# ---------------------------------------------------------------------------


def stream_generate(
    *,
    prompt: str,
    system_instruction: str,
    conversation_history: Optional[list[dict[str, str]]] = None,
    model_name: str = settings.GEMINI_MODEL,
    max_output_tokens: int = settings.MAX_RESPONSE_TOKENS,
    timeout_seconds: int = 30,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    """Stream a response from Gemini token by token.

    Wraps the regular generate() streaming API. Yields dicts with
    `type: "token"` and `content: str` for each chunk, then returns
    a final dict with full text and token counts (like generate()).

    Args:
        prompt: The assembled RAG prompt with context.
        system_instruction: System instruction for behaviour.
        conversation_history: Optional list of {"role", "content"} for multi-turn.
        model_name: Gemini model identifier.
        max_output_tokens: Max tokens in the response.
        timeout_seconds: Timeout for the API call.

    Yields:
        Dicts with "type": "token" and "content": str for each chunk.

    Returns:
        Dict with keys: text, prompt_tokens, completion_tokens, total_tokens, latency_ms.

    Raises:
        GeminiServiceError: On API errors or timeouts.
    """
    if not settings.GEMINI_API_KEY:
        raise GeminiServiceError("GEMINI_API_KEY is not configured")

    model = _get_model(model_name)
    start = time.time()

    # Build contents including history if provided
    contents = []
    if conversation_history:
        for msg in conversation_history:
            role = "model" if msg["role"] == "assistant" else msg["role"]
            contents.append({"role": role, "parts": [msg["content"]]})

    # Add the current prompt
    contents.append({"role": "user", "parts": [prompt]})

    try:
        stream = model.generate_content(
            contents,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_output_tokens,
                temperature=0.0,
                top_p=0.95,
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
            stream=True,
            request_options={"timeout": timeout_seconds * 1000},
        )

        full_text = ""
        for chunk in stream:
            if chunk.text:
                full_text += chunk.text
                yield {"type": "token", "content": chunk.text}

    except Exception as exc:
        elapsed_ms = (time.time() - start) * 1000
        logger.error(
            "gemini.stream_error",
            model=model_name,
            error=str(exc)[:300],
            latency_ms=round(elapsed_ms, 2),
        )
        raise GeminiServiceError(f"Gemini streaming failed: {exc}") from exc

    elapsed_ms = (time.time() - start) * 1000

    # Extract token usage from the last chunk if available
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    if full_text:
        try:
            if hasattr(stream, "usage_metadata") and stream.usage_metadata:
                prompt_tokens = stream.usage_metadata.prompt_token_count or 0
                completion_tokens = stream.usage_metadata.candidates_token_count or 0
                total_tokens = stream.usage_metadata.total_token_count or 0
        except Exception:
            pass

    logger.info(
        "gemini.stream_complete",
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=round(elapsed_ms, 2),
    )

    return {
        "text": full_text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": round(elapsed_ms, 2),
    }
