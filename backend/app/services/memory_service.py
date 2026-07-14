"""
Memory Service — CRUD, deduplication, and query operations.

Responsibilities:
  - Create, read, update, soft-delete, and bulk-delete memories
  - Enforce user ownership on every operation
  - Deduplicate new memories against existing ones
  - Return only active (non-deleted, is_active=True) memories for prompt injection
"""

import re
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, cast, func, or_
from sqlalchemy.orm import Session, Query

from app.core.config import settings
from app.services.cache_service import cache_service, invalidate_memory_cache
from app.core.cache_keys import memory_list_key
from app.core.datetime import utc_now
from app.core.logging import get_logger
from app.models.memory import Memory, MemoryType
from app.schemas.memory import MemoryCreate, MemoryUpdate, MemoryResponse

logger = get_logger("memory_service")


# ═══════════════════════════════════════════════════════════════════════
# Normalisation & Deduplication
# ═══════════════════════════════════════════════════════════════════════

# Stopwords for normalisation (English)
_STOPWORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "i", "me", "my",
    "we", "our", "you", "your", "he", "she", "it", "they", "them",
    "and", "or", "but", "if", "because", "as", "until", "while",
    "of", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below",
    "to", "from", "up", "down", "in", "out", "on", "off", "over",
    "under", "again", "further", "then", "once", "here", "there",
    "when", "where", "why", "how", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "also", "now", "this", "that", "these", "those",
}


def normalise_memory_text(text: str) -> str:
    """Normalise memory text for deduplication comparison.

    Strips punctuation, lowercases, removes stopwords, and sorts tokens.
    This produces a canonical form so that semantically similar memories
    (e.g. 'I like Python' vs 'Python is my favorite language')
    are treated as duplicates.
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    tokens = [t for t in text.split() if t not in _STOPWORDS]
    tokens.sort()
    return " ".join(tokens)


def find_duplicate(
    db: Session,
    user_id: uuid.UUID,
    memory_type: MemoryType,
    content: str,
) -> Optional[Memory]:
    """Check if a normalised version of this memory already exists.

    Returns the existing Memory if a duplicate is found, else None.
    Updates the found memory's `updated_at` timestamp to keep it fresh.
    """
    normalised = normalise_memory_text(content)

    existing = (
        db.query(Memory)
        .filter(
            Memory.user_id == user_id,
            Memory.memory_type == memory_type,
            Memory.deleted_at.is_(None),
        )
        .all()
    )

    for mem in existing:
        existing_normalised = normalise_memory_text(mem.content or mem.value)
        if existing_normalised == normalised:
            # Update timestamp to keep this memory fresh
            mem.updated_at = utc_now()
            db.commit()
            logger.info("memory.duplicate_updated_timestamp", memory_id=str(mem.id))
            return mem

    return None


# ═══════════════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════════════


def create_memory(
    db: Session,
    user_id: uuid.UUID,
    *,
    content: str,
    memory_type: MemoryType,
    confidence: float = 1.0,
    source_message_id: Optional[uuid.UUID] = None,
    is_active: bool = True,
) -> Memory:
    """Create a new memory after deduplication check.

    If a duplicate already exists, the existing memory's timestamp
    is updated and the existing object is returned instead.
    """
    # Deduplication check
    dup = find_duplicate(db, user_id, memory_type, content)
    if dup is not None:
        logger.info("memory.duplicate_skipped", memory_id=str(dup.id))
        return dup

    mem = Memory(
        user_id=user_id,
        key=_make_key(content, memory_type),
        value=content,
        content=content,
        memory_type=memory_type,
        confidence=confidence,
        source_message_id=source_message_id,
        is_active=is_active,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)

    logger.info(
        "memory.saved",
        memory_id=str(mem.id),
        memory_type=mem.memory_type.value,
        confidence=mem.confidence,
    )

    # Invalidate memory list cache
    invalidate_memory_cache(user_id)

    return mem


def _make_key(content: str, memory_type: MemoryType = MemoryType.FACT) -> str:
    """Generate a stable key from content for legacy column."""
    # Include memory_type prefix to maintain (user_id, key) uniqueness
    # when the same content has different types.
    cleaned = content.lower().strip()[:76]
    return f"{memory_type.value}:{cleaned}" if cleaned else f"{memory_type.value}:memory"


def get_memory(
    db: Session,
    memory_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[Memory]:
    """Get a single memory by ID, enforcing user ownership."""
    return (
        db.query(Memory)
        .filter(
            Memory.id == memory_id,
            Memory.user_id == user_id,
        )
        .first()
    )


def list_memories(
    db: Session,
    user_id: uuid.UUID,
    *,
    memory_type: Optional[MemoryType] = None,
    is_active: Optional[bool] = None,
    include_deleted: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Memory], int]:
    """List memories for a user with optional filters and caching.

    Cache key includes all filter parameters so different views of the
    data are cached independently. Invalidated on create / update /
    delete / bulk-delete.
    """
    # Build cache key for this exact filter combination
    cache_key = memory_list_key(user_id, memory_type, is_active, include_deleted)
    cached = cache_service.get(cache_key)
    if cached is not None:
        # Cached data is a list of dicts plus total count
        cached_memories = cached.get("memories", [])
        cached_total = cached.get("total", 0)
        # Convert dicts back to Memory ORM objects
        memories = [
            db.query(Memory).filter(Memory.id == m["id"]).first()
            for m in cached_memories
        ]
        memories = [m for m in memories if m is not None]
        return memories, cached_total

    query: Query = db.query(Memory).filter(Memory.user_id == user_id)

    # Soft-delete filter
    if not include_deleted:
        query = query.filter(Memory.deleted_at.is_(None))

    # Memory type filter
    if memory_type is not None:
        query = query.filter(Memory.memory_type == memory_type)

    # Active filter
    if is_active is not None:
        query = query.filter(Memory.is_active == is_active)

    # Count total before pagination
    all_results: list[Memory] = query.order_by(Memory.updated_at.desc()).all()
    total = len(all_results)

    # Cache the full result set so any page benefits from cached data
    cache_service.set(
        cache_key,
        {
            "memories": [
                MemoryResponse.model_validate(m).model_dump() for m in all_results
            ],
            "total": total,
        },
        ttl=settings.CACHE_MEMORY_TTL,
    )

    # Paginate
    start = (page - 1) * page_size
    memories = all_results[start:start + page_size]

    return memories, total


def get_active_memories(
    db: Session,
    user_id: uuid.UUID,
    *,
    limit: int = 20,
) -> list[Memory]:
    """Get active, non-deleted memories for prompt injection."""
    return (
        db.query(Memory)
        .filter(
            Memory.user_id == user_id,
            Memory.deleted_at.is_(None),
            Memory.is_active == True,  # noqa: E712
        )
        .order_by(Memory.confidence.desc(), Memory.updated_at.desc())
        .limit(limit)
        .all()
    )


def update_memory(
    db: Session,
    memory_id: uuid.UUID,
    user_id: uuid.UUID,
    updates: MemoryUpdate,
) -> Optional[Memory]:
    """Update a memory, enforcing user ownership."""
    mem = get_memory(db, memory_id, user_id)
    if mem is None:
        return None

    changed = False
    if updates.content is not None:
        mem.content = updates.content
        mem.value = updates.content  # keep legacy field in sync
        mem.key = _make_key(updates.content)
        changed = True
    if updates.type is not None:
        mem.memory_type = updates.type  # type: ignore[assignment]  # schemas share same enum values
        changed = True
    if updates.is_active is not None:
        mem.is_active = updates.is_active
        changed = True

    if changed:
        mem.updated_at = utc_now()
        db.commit()
        db.refresh(mem)
        logger.info("memory.updated", memory_id=str(mem.id))
        # Invalidate memory list cache
        invalidate_memory_cache(user_id, mem.memory_type)
        invalidate_memory_cache(user_id)

    return mem


def soft_delete_memory(
    db: Session,
    memory_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Soft-delete a memory, enforcing user ownership."""
    mem = get_memory(db, memory_id, user_id)
    if mem is None:
        return False

    mem.deleted_at = utc_now()
    mem.is_active = False
    db.commit()
    logger.info("memory.deleted", memory_id=str(mem.id))
    # Invalidate memory list cache
    invalidate_memory_cache(user_id)
    return True


def bulk_delete_memories(
    db: Session,
    user_id: uuid.UUID,
) -> int:
    """Soft-delete ALL memories for a user ('Forget Everything')."""
    now = utc_now()
    count = (
        db.query(Memory)
        .filter(
            Memory.user_id == user_id,
            Memory.deleted_at.is_(None),
        )
        .update(
            {"deleted_at": now, "is_active": False, "updated_at": now},
            synchronize_session=False,
        )
    )
    db.commit()
    logger.info("memory.bulk_deleted", user_id=str(user_id), count=count)
    # Invalidate all memory list caches for this user
    invalidate_memory_cache(user_id)
    return count
