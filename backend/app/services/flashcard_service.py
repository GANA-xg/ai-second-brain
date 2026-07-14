"""
Flashcard generation service.

Produces flashcards from document chunks via Gemini, validates output,
and persists valid cards linked to their source chunks.
"""
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.flashcard import Flashcard, FlashcardDifficulty
from app.services.llm_service import generate as gemini_generate
from app.services.prompt_service import (
    FLASHCARD_SYSTEM_INSTRUCTION,
    format_flashcard_prompt,
)
from app.services.cache_service import invalidate_search_cache
from app.core.logging import get_logger
from app.schemas.flashcard import FlashcardResponse

logger = get_logger("app.services.flashcard")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BATCH_SIZE = settings.FLASHCARD_BATCH_SIZE
_MAX_PER_BATCH = settings.FLASHCARD_MAX_PER_BATCH
_FLASHCARD_MODEL = settings.FLASHCARD_MODEL
_FLASHCARD_TIMEOUT = settings.FLASHCARD_TIMEOUT_SECONDS

# Pattern to strip markdown code fences from Gemini output
_CODE_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?```",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


def clean_gemini_response(text: str) -> str:
    """Strip code fences, markdown, and leading/trailing noise from Gemini output.

    1. Remove ```json ... ``` or ``` ... ``` code fences.
    2. Strip any surrounding whitespace.
    3. If the result doesn't start with '[' or '{', try to find the first
       '[' or '{' and discard everything before it.
    """
    # Remove code fences
    match = _CODE_FENCE_PATTERN.search(text)
    if match:
        text = match.group(1)

    text = text.strip()

    # Find first JSON character if text starts with noise
    if text and text[0] not in ("[", "{"):
        for prefix in ("[", "{"):
            idx = text.find(prefix)
            if idx != -1:
                text = text[idx:]
                break

    # Remove trailing noise after the last ] or }
    if text:
        last_bracket = text.rfind("]")
        last_brace = text.rfind("}")
        last_valid = max(last_bracket, last_brace)
        if last_valid != -1:
            text = text[: last_valid + 1]

    return text.strip()


def parse_flashcard_json(text: str) -> list[dict[str, Any]]:
    """Parse cleaned Gemini output as a JSON array of flashcard objects.

    Returns:
        List of parsed card dicts. If parsing fails, returns an empty list
        and logs the error — never raises.
    """
    cleaned = clean_gemini_response(text)
    if not cleaned:
        logger.warning("Gemini returned empty response after cleaning")
        return []

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Gemini output is not valid JSON: %s | text=%.200s", exc, cleaned)
        return []

    if isinstance(parsed, dict):
        # Single card object wrapped in dict instead of array
        parsed = [parsed]

    if not isinstance(parsed, list):
        logger.warning("Gemini output is not a list: type=%s", type(parsed).__name__)
        return []

    return parsed


def validate_card(card: dict[str, Any]) -> dict[str, Any] | None:
    """Validate a single flashcard dict.

    Required fields:
        - front: non-empty string (also accepted as 'question')
        - back: non-empty string (also accepted as 'answer')

    Returns the validated card dict with normalized 'front'/'back' keys,
    or None if the card is invalid.
    """
    front = card.get("front") or card.get("question")
    back = card.get("back") or card.get("answer")

    if not isinstance(front, str) or not front.strip():
        return None
    if not isinstance(back, str) or not back.strip():
        return None

    return {
        "front": front.strip(),
        "back": back.strip(),
    }


# ---------------------------------------------------------------------------
# Chunk batching
# ---------------------------------------------------------------------------


def batch_chunks(chunks: list[Chunk], batch_size: int = _BATCH_SIZE) -> list[list[Chunk]]:
    """Group chunks into batches for Gemini requests."""
    return [chunks[i : i + batch_size] for i in range(0, len(chunks), batch_size)]


# ---------------------------------------------------------------------------
# Flashcard CRUD helpers
# ---------------------------------------------------------------------------


def _get_document_or_404(db: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    """Get a document by ID, verifying ownership. Raises 404 if not found."""
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user_id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


def _get_flashcard_or_404(db: Session, flashcard_id: uuid.UUID, user_id: uuid.UUID) -> Flashcard:
    """Get a flashcard by ID, verifying ownership. Raises 404 if not found."""
    card = (
        db.query(Flashcard)
        .filter(Flashcard.id == flashcard_id, Flashcard.user_id == user_id)
        .first()
    )
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flashcard not found",
        )
    return card


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------


def generate_flashcards(
    db: Session,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    """Generate flashcards from a document's chunks via Gemini.

    Flows:
        1. Verify document exists and belongs to user.
        2. Load all chunks for the document.
        3. Group chunks into batches of BATCH_SIZE.
        4. For each batch, call Gemini to generate cards.
        5. Parse, validate, and store cards.
        6. Return statistics.

    Args:
        db: Database session.
        user_id: Owning user's UUID.
        document_id: Target document's UUID.

    Returns:
        Dict with message, generated_count, discarded_count, total_count.
    """
    doc = _get_document_or_404(db, document_id, user_id)

    if doc.status not in (DocumentStatus.READY,):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot generate flashcards: document status is '{doc.status.value}'. "
                "Document must be READY."
            ),
        )

    # Load all chunks
    chunks: list[Chunk] = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .all()
    )

    if not chunks:
        return {
            "message": "No chunks found for this document. No flashcards generated.",
            "generated_count": 0,
            "discarded_count": 0,
            "total_count": 0,
        }

    # Batch chunks
    batches = batch_chunks(chunks)

    total_generated = 0
    total_discarded = 0
    total_stored = 0

    logger.info(
        "Flashcard generation start",
        extra={
            "document_id": str(document_id),
            "user_id": str(user_id),
            "chunk_count": len(chunks),
            "batch_count": len(batches),
        },
    )

    # Call Gemini for each batch
    for batch_idx, batch in enumerate(batches):
        # Combine chunk text for this batch
        combined_text = "\n\n".join(
            f"[Chunk {c.chunk_index}] {c.content}" for c in batch
        )

        # Build prompt and call Gemini
        prompt = format_flashcard_prompt(combined_text)
        start_time = time.monotonic()

        try:
            response = gemini_generate(
                prompt=prompt,
                system_instruction=FLASHCARD_SYSTEM_INSTRUCTION,
                model_name=_FLASHCARD_MODEL,
                timeout_seconds=_FLASHCARD_TIMEOUT,
            )
            raw_text = response["text"]
        except Exception as exc:
            logger.error(
                "Gemini call failed for batch %d/%d",
                batch_idx + 1,
                len(batches),
                extra={
                    "error": str(exc),
                    "document_id": str(document_id),
                    "batch_index": batch_idx,
                },
            )
            continue

        gemini_latency = time.monotonic() - start_time

        # Parse response
        raw_cards = parse_flashcard_json(raw_text)

        if not raw_cards:
            logger.info(
                "No cards parsed from batch %d/%d",
                batch_idx + 1,
                len(batches),
                extra={
                    "document_id": str(document_id),
                    "gemini_latency_s": round(gemini_latency, 2),
                },
            )
            continue

        # Validate and store
        batch_generated = len(raw_cards)
        batch_discarded = 0
        batch_stored = 0

        for card_dict in raw_cards:
            validated = validate_card(card_dict)
            if validated is None:
                batch_discarded += 1
                logger.debug(
                    "Discarded invalid flashcard",
                    extra={"raw": str(card_dict)[:200]},
                )
                continue

            # Store with provenance — link to first chunk in batch or
            # try to infer from a `chunk_id` field in the return (unlikely)
            source_chunk_id = batch[0].id

            card = Flashcard(
                user_id=user_id,
                document_id=document_id,
                source_chunk_id=source_chunk_id,
                question=validated["front"],
                answer=validated["back"],
                difficulty=FlashcardDifficulty.MEDIUM,
            )
            db.add(card)
            batch_stored += 1

        db.commit()

        total_generated += batch_generated
        total_discarded += batch_discarded
        total_stored += batch_stored

        logger.info(
            "Batch %d/%d done",
            batch_idx + 1,
            len(batches),
            extra={
                "document_id": str(document_id),
                "generated": batch_generated,
                "discarded": batch_discarded,
                "stored": batch_stored,
                "gemini_latency_s": round(gemini_latency, 2),
            },
        )

    # Invalidate search cache since new cards were created
    invalidate_search_cache(user_id)

    logger.info(
        "Flashcard generation finish",
        extra={
            "document_id": str(document_id),
            "user_id": str(user_id),
            "total_generated": total_generated,
            "total_discarded": total_discarded,
            "total_stored": total_stored,
        },
    )

    return {
        "message": (
            f"Generated {total_stored} flashcards "
            f"({total_discarded} discarded from {total_generated} raw)"
        ),
        "generated_count": total_stored,
        "discarded_count": total_discarded,
        "total_count": total_stored,
    }


def list_flashcards(
    db: Session,
    user_id: uuid.UUID,
    *,
    document_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List flashcards for a user, optionally filtered by document.

    Returns a paginated response matching the project's pagination style.
    """
    query = db.query(Flashcard).filter(
        Flashcard.user_id == user_id,
        Flashcard.deleted_at.is_(None),
    )

    if document_id is not None:
        query = query.filter(Flashcard.document_id == document_id)

    total = query.count()

    query = query.order_by(Flashcard.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    cards = query.all()

    return {
        "flashcards": [FlashcardResponse.model_validate(c) for c in cards],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


def update_flashcard(
    db: Session,
    user_id: uuid.UUID,
    flashcard_id: uuid.UUID,
    *,
    front: str | None = None,
    back: str | None = None,
) -> Flashcard:
    """Update a flashcard's front/back text. Ownership required."""
    card = _get_flashcard_or_404(db, flashcard_id, user_id)

    if front is not None:
        card.question = front.strip()
    if back is not None:
        card.answer = back.strip()

    db.commit()
    db.refresh(card)
    return card


def delete_flashcard(
    db: Session,
    user_id: uuid.UUID,
    flashcard_id: uuid.UUID,
) -> None:
    """Soft-delete a flashcard. Ownership required."""
    card = _get_flashcard_or_404(db, flashcard_id, user_id)

    card.deleted_at = datetime.now(timezone.utc)
    db.commit()


def delete_document_flashcards(
    db: Session,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> int:
    """Soft-delete all flashcards belonging to a document. Ownership required."""
    doc = _get_document_or_404(db, document_id, user_id)

    now = datetime.now(timezone.utc)
    count = (
        db.query(Flashcard)
        .filter(
            Flashcard.document_id == document_id,
            Flashcard.user_id == user_id,
            Flashcard.deleted_at.is_(None),
        )
        .update({"deleted_at": now})
    )
    db.commit()
    return count
