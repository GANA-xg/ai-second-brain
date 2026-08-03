"""Cache key generation utilities."""

import hashlib
from typing import Optional
from uuid import UUID

from app.models.memory import MemoryType


def md5_hash(text: str) -> str:
    """Return MD5 hash of a string as hex digest."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def search_key(user_id: UUID, query: str, document_ids: Optional[list[UUID]] = None) -> str:
    """Generate cache key for search results.

    Format: search:{user_id}:{md5(query)}:{md5(document_ids)}
    """
    query_hash = md5_hash(query)
    if document_ids:
        doc_hash = md5_hash(",".join(str(d) for d in sorted(document_ids)))
    else:
        doc_hash = "all"
    return f"search:{user_id}:{query_hash}:{doc_hash}"


def document_list_key(user_id: UUID) -> str:
    """Generate cache key for user's document list.

    Format: docs:{user_id}
    """
    return f"docs:{user_id}"


def memory_list_key(
    user_id: UUID,
    memory_type: Optional[MemoryType] = None,
    is_active: Optional[bool] = None,
    include_deleted: bool = False,
) -> str:
    """Generate cache key for user's memory list with filters.

    Format: memories:{user_id}:{hash(filter_string)}
    """
    # Convert enum to string for consistent hashing
    mt_str = memory_type.value if memory_type is not None else "None"
    filter_str = f"{mt_str}:{is_active}:{include_deleted}"
    filter_hash = md5_hash(filter_str)
    return f"memories:{user_id}:{filter_hash}"


def conversation_list_key(user_id: UUID) -> str:
    """Generate cache key for user's conversation list.

    Format: conversations:{user_id}
    """
    return f"conversations:{user_id}"


def conversation_messages_key(conversation_id: UUID, page: int, page_size: int) -> str:
    """Generate cache key for paginated conversation messages.

    Format: messages:{conversation_id}:{page}:{page_size}
    """
    return f"messages:{conversation_id}:{page}:{page_size}"


def conversation_summary_key(conversation_id: UUID) -> str:
    """Generate cache key for conversation summary.

    Format: conversation:{conversation_id}
    """
    return f"conversation:{conversation_id}"


def quiz_list_key(user_id: UUID, document_id: UUID | None = None) -> str:
    """Generate cache key for quiz list.

    Format: quizzes:{user_id}:{document_id or '*'}
    """
    doc_part = str(document_id) if document_id else "*"
    return f"quizzes:{user_id}:{doc_part}"


def quiz_detail_key(quiz_id: UUID) -> str:
    """Generate cache key for a single quiz.

    Format: quiz:{quiz_id}
    """
    return f"quiz:{quiz_id}"


def quiz_attempt_list_key(quiz_id: UUID, page: int = 1, page_size: int = 20) -> str:
    """Generate cache key for paginated attempt list.

    Format: attempts:{quiz_id}:{page}:{page_size}
    """
    return f"attempts:{quiz_id}:{page}:{page_size}"
