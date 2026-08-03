"""Generate audio overviews: a two-speaker discussion script from selected source chunks.

Given a set of document IDs, fetches their chunks from the database, prompts Gemini
to generate a short podcast-style discussion script, and returns the script text.

TTS integration: The returned script can be synthesized via:
  - Web Speech API (SpeechSynthesisUtterance) in the browser — free, no API key
  - Google Cloud Text-to-Speech (pip install google-cloud-texttospeech)
  - Edge-TTS (pip install edge-tts) — free, multi-voice
  - ElevenLabs API

ponytail: currently returns script text only. Add TTS when a provider API key is configured.
"""

import time
import uuid
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.services.llm_service import generate as gemini_generate

logger = get_logger("audio_overview_service")

AUDIO_OVERVIEW_SYSTEM_INSTRUCTION = (
    "You are a podcast producer creating an engaging two-speaker discussion about document content. "
    "Your output must be ONLY valid JSON — no markdown, no code fences, no extra text. "
    'Return a JSON object with a "script" field containing the discussion text.'
)

def format_overview_prompt(context: str) -> str:
    """Build the audio overview prompt for a body of context text."""
    return (
        "Write a short, engaging two-speaker discussion (a 'podcast script') based on the content below.\n\n"
        "Format:\n"
        "- Speaker A (Host): introduces topics, asks questions, summarizes\n"
        "- Speaker B (Expert): explains concepts, provides details, gives examples\n\n"
        "Rules:\n"
        "- Make it natural and conversational, like a real podcast\n"
        "- Keep it under 3 minutes when read aloud (~400-500 words)\n"
        "- Stay strictly factual — base everything on the provided content\n"
        "- Use simple labels like 'Host:' and 'Expert:' before each line\n"
        "- Include a brief intro and wrap-up\n\n"
        f"Content:\n{context}\n\n"
        'Return ONLY a JSON object: {{"script": "Host: ...\\nExpert: ..."}}'
    )


def generate_audio_overview(
    db: Session,
    user_id: uuid.UUID,
    document_ids: list[uuid.UUID],
) -> dict[str, Any]:
    """Generate a two-speaker discussion script from selected documents' chunks.

    Args:
        db: SQLAlchemy session.
        user_id: The requesting user's UUID.
        document_ids: List of document UUIDs to source content from.

    Returns:
        dict with keys:
          - script: the two-speaker discussion text
          - chunk_count: number of chunks used
          - generated_at: ISO timestamp
    """
    start_time = time.monotonic()

    # Fetch chunks for the selected documents (owned by this user)
    stmt = (
        select(Chunk)
        .where(Chunk.document_id.in_(document_ids))
        .order_by(Chunk.document_id, Chunk.chunk_index)
    )
    chunks = list(db.execute(stmt).scalars().all())

    if not chunks:
        return {
            "script": "",
            "chunk_count": 0,
            "note": "No chunks found for the selected documents.",
        }

    # Build context from chunks (truncate to avoid token limits)
    full_text = "\n\n".join(c.content for c in chunks)
    max_chars = 12_000  # ponytail: rough limit; improve with token-aware truncation
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "\n\n[...truncated]"

    logger.info(
        "audio_overview.generating",
        document_count=len(document_ids),
        chunk_count=len(chunks),
        context_length=len(full_text),
    )

    system = AUDIO_OVERVIEW_SYSTEM_INSTRUCTION
    prompt = format_overview_prompt(full_text)

    try:
        response = gemini_generate(
            system_instruction=system,
            prompt=prompt,
            model_name=settings.FLASHCARD_MODEL,
        )
        raw_text = response.get("text", "")

    except Exception as exc:
        logger.error("audio_overview.gemini_failed", error=str(exc))
        return {
            "script": "",
            "chunk_count": len(chunks),
            "error": f"Gemini generation failed: {exc}",
        }

    import json

    cleaned = raw_text.lstrip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        script = result.get("script", cleaned)
    except json.JSONDecodeError:
        # Response wasn't valid JSON — use raw text
        script = cleaned

    elapsed = time.monotonic() - start_time
    logger.info(
        "audio_overview.generated",
        script_length=len(script),
        elapsed_s=round(elapsed, 2),
    )

    return {
        "script": script,
        "chunk_count": len(chunks),
    }
