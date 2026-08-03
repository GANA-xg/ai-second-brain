"""Message CRUD service with pagination and lifecycle tracking."""

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.message import Message, MessageRole, MessageStatus
from app.services.cache_service import cache_service, invalidate_message_cache, invalidate_conversation_cache
from app.core.cache_keys import conversation_messages_key
from app.services.conversation_service import (
    ConversationNotFoundError,
    ConversationAccessDeniedError,
    get_conversation,
    auto_title_from_message,
)

logger = get_logger("message_service")


def save_user_message(
    db: Session,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
) -> Message:
    """Save a user message before calling the AI pipeline.

    If this is the first message in the conversation, auto-generate
    a title from the content.

    Raises:
        ConversationNotFoundError: If the conversation doesn't exist.
        ConversationAccessDeniedError: If the user doesn't own it.
    """
    conv = get_conversation(db, conversation_id, user_id)

    # Auto-title if still the default placeholder
    if conv.title == "New conversation" and content.strip():
        conv.title = auto_title_from_message(content)
        db.flush()

    msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    logger.info(
        "message.saved",
        message_id=str(msg.id),
        conversation_id=str(conversation_id),
        role="USER",
    )
    # Invalidate message cache for this conversation + conversation list
    invalidate_message_cache(conversation_id)
    invalidate_conversation_cache(user_id)
    return msg


def save_assistant_message(
    db: Session,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
    status: MessageStatus = MessageStatus.COMPLETED,
    citations: Optional[list[dict[str, Any]]] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    error_metadata: Optional[dict[str, Any]] = None,
) -> Message:
    """Save an assistant message after the AI pipeline completes (or fails)."""
    # Verify ownership
    get_conversation(db, conversation_id, user_id)

    msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=content,
        status=status,
        citations=citations or [],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        error_metadata=error_metadata,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    log_status = "completed" if status == MessageStatus.COMPLETED else status.value.lower()
    logger.info(
        f"message.{log_status}",
        message_id=str(msg.id),
        conversation_id=str(conversation_id),
        role="ASSISTANT",
        status=status.value if status else None,
    )
    # Invalidate message cache for this conversation + conversation list
    invalidate_message_cache(conversation_id)
    invalidate_conversation_cache(user_id)
    return msg


def get_messages(
    db: Session,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = settings.DEFAULT_PAGE_SIZE,
) -> tuple[list[Message], int, bool]:
    """Get paginated messages for a conversation with ownership check and caching.

    Returns (messages, total_count, has_next).
    """
    # Ownership check
    get_conversation(db, conversation_id, user_id)

    page_size = min(page_size, settings.MAX_PAGE_SIZE)

    # Try cache
    cache_key = conversation_messages_key(conversation_id, page, page_size)
    cached = cache_service.get(cache_key)
    if cached is not None:
        msg_ids = cached.get("message_ids", [])
        cached_total = cached.get("total", 0)
        cached_has_next = cached.get("has_next", False)
        # msg_ids arrive as strings after JSON deserialization, but
        # UUID(as_uuid=True) needs uuid.UUID instances for the bind
        uuids = [uuid.UUID(mid) for mid in msg_ids]
        by_id = {m.id: m for m in db.query(Message).filter(Message.id.in_(uuids)).all()}
        messages = [by_id[u] for u in uuids if u in by_id]
        return messages, cached_total, cached_has_next

    total = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .count()
    )

    offset = (page - 1) * page_size

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    has_next = (offset + page_size) < total

    # Cache
    cache_service.set(
        cache_key,
        {
            "message_ids": [str(m.id) for m in messages],
            "total": total,
            "has_next": has_next,
        },
        ttl=settings.CACHE_MESSAGE_TTL,
    )

    return messages, total, has_next


def get_conversation_history(
    db: Session,
    conversation_id: uuid.UUID,
    max_messages: int = settings.MAX_HISTORY_MESSAGES,
) -> list[dict[str, str]]:
    """Load the recent message history for context injection.

    Returns a list of dicts with 'role' and 'content' keys, formatted
    for inclusion in the RAG prompt. Only the last `max_messages`
    messages are returned (to stay within token budget).
    """
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(max_messages)
        .all()
    )
    # Reverse to chronological order
    messages.reverse()
    return [
        {"role": msg.role.value.lower(), "content": msg.content}
        for msg in messages
    ]


def get_last_user_message(
    db: Session,
    conversation_id: uuid.UUID,
) -> Optional[str]:
    """Get the most recent user message content, or None."""
    msg = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == MessageRole.USER,
        )
        .order_by(Message.created_at.desc())
        .first()
    )
    return msg.content if msg else None
