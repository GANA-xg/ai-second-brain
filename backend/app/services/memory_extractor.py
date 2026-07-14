"""
Memory Extractor — background extraction of durable memories from conversations.

Uses Gemini to analyse the latest conversation exchange and extract
durable long-term memories. Runs as a FastAPI BackgroundTask so the
user never waits for extraction.
"""

import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.memory import MemoryType
from app.services.llm_service import generate, LLMError
from app.services.memory_service import create_memory

logger = get_logger("memory_extractor")

# ── Extraction Prompt ────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are a memory extraction assistant. Your task is to analyse conversations and extract durable long-term memories about the user.

Extract only:
- PREFERENCE: Things the user likes, dislikes, or prefers
- GOAL: Things the user wants to achieve or learn
- FACT: Verifiable facts the user has stated about themselves

Ignore:
- Temporary requests or one-off questions
- Document contents or file references
- Chat instructions or commands
- System prompts or instructions
- Politeness markers ("thanks", "please", etc.)
- Follow-up clarifications

Rules:
- Each memory must be a complete, standalone statement
- Prefer specific facts over vague generalities
- Extract multiple memories if the exchange contains several distinct facts
- If NO durable memory can be extracted, return {"memories": null}
- Do NOT return prose — only return valid JSON

Return exactly this JSON structure:
{"memories": [{"type": "goal", "content": "User wants to learn Rust", "confidence": 0.95}]}

Memory types: "preference", "goal", "fact".
Confidence must be a float between 0.0 and 1.0.
"""


def extract_memories_from_exchange(
    *,
    user_message: str,
    assistant_response: str,
    user_id: uuid.UUID,
    source_message_id: uuid.UUID,
    db: Session,
) -> list[dict]:
    """Analyse the latest conversation exchange and extract memories.

    Runs synchronously — intended to be called from within a
    FastAPI BackgroundTask so the caller returns immediately.

    Args:
        user_message: The user's latest question/message.
        assistant_response: The AI's response to that message.
        user_id: Who the memory belongs to.
        source_message_id: The assistant message ID that generated this.
        db: Database session (new session for background task).

    Returns:
        List of memory dicts that were saved (empty on failure).
    """
    if not settings.ENABLE_AUTO_MEMORY:
        logger.info("memory_extraction.disabled")
        return []

    logger.info("memory_extraction.started", user_id=str(user_id))

    # Build the extraction prompt
    extraction_prompt = (
        f"Analyse this conversation exchange for durable memories:\n\n"
        f"User: {user_message}\n\n"
        f"Assistant: {assistant_response}"
    )

    try:
        result = generate(
            prompt=extraction_prompt,
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            model_name=settings.MEMORY_EXTRACTION_MODEL,
            max_output_tokens=1024,
            timeout_seconds=settings.MEMORY_EXTRACTION_TIMEOUT,
        )
    except LLMError as exc:
        logger.error(
            "memory_extraction.gemini_failed",
            user_id=str(user_id),
            error=str(exc)[:200],
        )
        return []

    raw_text = result.get("text", "").strip()
    if not raw_text:
        logger.info("memory_extraction.empty_response", user_id=str(user_id))
        return []

    # Parse JSON from response
    memories_data = _parse_extraction_json(raw_text)
    if memories_data is None:
        logger.info("memory_extraction.invalid_json", user_id=str(user_id))
        return []

    saved_memories = []
    for mem_item in memories_data:
        mem_type_str = mem_item.get("type", "").upper()
        content = mem_item.get("content", "").strip()
        confidence = float(mem_item.get("confidence", 0.0))

        # Validate type
        try:
            mem_type = MemoryType(mem_type_str)
        except (ValueError, KeyError):
            logger.warning(
                "memory_extraction.invalid_type",
                type=mem_type_str,
            )
            continue

        # Validate content
        if not content:
            continue

        # Confidence filter
        if confidence < settings.MEMORY_MIN_CONFIDENCE:
            logger.info(
                "memory_extraction.low_confidence",
                confidence=confidence,
                threshold=settings.MEMORY_MIN_CONFIDENCE,
                content_preview=content[:60],
            )
            continue

        # Save
        try:
            mem = create_memory(
                db,
                user_id,
                content=content,
                memory_type=mem_type,
                confidence=confidence,
                source_message_id=source_message_id,
            )
            saved_memories.append({
                "id": str(mem.id),
                "type": mem.memory_type.value,
                "content": mem.content,
                "confidence": mem.confidence,
            })
        except Exception as exc:
            logger.error(
                "memory_extraction.save_failed",
                user_id=str(user_id),
                error=str(exc)[:200],
            )

    logger.info(
        "memory_extraction.completed",
        user_id=str(user_id),
        extracted=len(memories_data) if memories_data else 0,
        saved=len(saved_memories),
    )
    return saved_memories


def _parse_extraction_json(raw_text: str) -> Optional[list[dict]]:
    """Parse the JSON from Gemini's response.

    Handles markdown-wrapped JSON (```json ... ```) and trailing prose.
    """
    # Try to extract from markdown code block first
    if "```json" in raw_text:
        # Grab content between ```json and the closing ```
        parts = raw_text.split("```json", 1)
        if len(parts) > 1:
            inner = parts[1]
            if "```" in inner:
                inner = inner.split("```", 1)[0]
            raw_text = inner.strip()
    elif "```" in raw_text:
        parts = raw_text.split("```", 1)
        if len(parts) > 1:
            inner = parts[1]
            if "```" in inner:
                inner = inner.split("```", 1)[0]
            raw_text = inner.strip()

    # Try to find JSON object/array boundaries
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        logger.warning("memory_extraction.no_json_found", raw=raw_text[:200])
        return None

    json_str = raw_text[start : end + 1]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.warning(
            "memory_extraction.json_parse_error",
            error=str(exc)[:200],
        )
        return None

    memories = data.get("memories")
    if memories is None:
        logger.info("memory_extraction.no_memories_found")
        return None

    if not isinstance(memories, list):
        logger.warning("memory_extraction.not_a_list")
        return None

    return memories
