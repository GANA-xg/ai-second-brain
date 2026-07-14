"""Cache service layer: convenience wrappers + centralized invalidation.

This module provides:

* Direct CRUD helpers (get / set / delete / delete_pattern / exists / ttl)
* Centralized invalidation functions for each domain (documents, memories,
  conversations, messages, search)
* All functions are synchronous and degrade gracefully when Redis is down.

Usage:

    from app.services.cache_service import cache_service

    cache_service.set("my-key", {"data": 42}, ttl=120)
    value = cache_service.get("my-key")
    cache_service.delete("my-key")

    # -- invalidation --
    from app.services.cache_service import invalidate_memory_cache
    invalidate_memory_cache(user_id)
"""

import logging
from typing import Any, Optional
from uuid import UUID, uuid4

from app.core.cache import redis_cache
from app.core.cache_keys import (
    conversation_list_key,
    conversation_messages_key,
    document_list_key,
    memory_list_key,
    search_key,
    quiz_list_key,
    quiz_detail_key,
)
from app.core.config import settings
from app.models.memory import MemoryType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Direct cache helpers (thin wrappers over RedisCache)
# ═══════════════════════════════════════════════════════════════════════


class CacheService:
    """Convenience wrapper that adds structured logging on top of RedisCache.

    Every method is safe to call when Redis is unavailable — they
    log a warning and return a sensible default.
    """

    # -- core ops -------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Get a deserialized value from cache.
        Returns None on miss or when Redis is down."""
        return redis_cache.get(key)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store a value with optional TTL (defaults to CACHE_DEFAULT_TTL)."""
        return redis_cache.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        """Delete a single key."""
        return redis_cache.delete(key)

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern."""
        return redis_cache.delete_pattern(pattern)

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return redis_cache.exists(key)

    def ttl(self, key: str) -> int:
        """Get remaining TTL (-2 = missing, -1 = no expiry)."""
        return redis_cache.ttl(key)

    # -- metrics --------------------------------------------------------

    @property
    def hit_rate(self) -> float:
        return redis_cache.hit_rate

    def flush_metrics(self) -> dict:
        return redis_cache.flush_metrics()


# Singleton — import this from everywhere.
cache_service = CacheService()


# ═══════════════════════════════════════════════════════════════════════
# Centralized invalidation helpers
# ═══════════════════════════════════════════════════════════════════════

# Each function encapsulates the exact key(s) to delete so that
# callers never need to construct or know about cache key formats.
# Always delete (no-op when Redis is down).


def invalidate_document_cache(user_id: UUID) -> None:
    """Invalidate the cached document list for *user_id*."""
    key = document_list_key(user_id)
    cache_service.delete(key)
    logger.debug("cache.invalidate document user=%s key=%s", user_id, key)


def invalidate_memory_cache(
    user_id: UUID,
    memory_type: Optional[MemoryType] = None,
) -> None:
    """Invalidate memory list caches for *user_id*.

    When *memory_type* is provided, only that filter's cache entry is
    deleted. Otherwise all memory-list entries for the user are cleared
    via pattern match.
    """
    if memory_type:
        key = memory_list_key(user_id, memory_type)
        cache_service.delete(key)
        logger.debug("cache.invalidate memory user=%s type=%s", user_id, memory_type)
    else:
        pattern = f"memories:{user_id}:*"
        count = cache_service.delete_pattern(pattern)
        logger.debug(
            "cache.invalidate memory user=%s pattern=%s count=%s",
            user_id, pattern, count,
        )


def invalidate_conversation_cache(user_id: UUID) -> None:
    """Invalidate the cached conversation list for *user_id*."""
    key = conversation_list_key(user_id)
    cache_service.delete(key)
    logger.debug("cache.invalidate conversation user=%s key=%s", user_id, key)


def invalidate_message_cache(conversation_id: UUID) -> None:
    """Invalidate ALL cached message pages for a conversation."""
    pattern = f"messages:{conversation_id}:*"
    count = cache_service.delete_pattern(pattern)
    logger.debug(
        "cache.invalidate messages conversation=%s count=%s",
        conversation_id, count,
    )


def invalidate_search_cache(user_id: UUID) -> None:
    """Invalidate ALL cached search results for *user_id*."""
    pattern = f"search:{user_id}:*"
    count = cache_service.delete_pattern(pattern)
    logger.debug(
        "cache.invalidate search user=%s count=%s",
        user_id, count,
    )


def invalidate_quiz_cache(user_id: UUID, quiz_id: UUID | None = None) -> None:
    """Invalidate quiz caches for *user_id*.

    When *quiz_id* is provided, also deletes that specific quiz detail cache.
    """
    # Invalidate all quiz list caches for this user
    pattern = f"quizzes:{user_id}:*"
    count = cache_service.delete_pattern(pattern)
    logger.debug(
        "cache.invalidate quiz list user=%s count=%s",
        user_id, count,
    )

    if quiz_id:
        key = quiz_detail_key(quiz_id)
        cache_service.delete(key)
        logger.debug("cache.invalidate quiz detail quiz=%s", quiz_id)

    # Also invalidate attempt caches
    if quiz_id:
        attempt_pattern = f"attempts:{quiz_id}:*"
        attempt_count = cache_service.delete_pattern(attempt_pattern)
        logger.debug(
            "cache.invalidate quiz attempts quiz=%s count=%s",
            quiz_id, attempt_count,
        )
