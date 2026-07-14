"""Conversation CRUD service with ownership enforcement and caching."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.cache_service import cache_service, invalidate_conversation_cache, invalidate_message_cache
from app.core.cache_keys import conversation_list_key

logger = get_logger("conversation_service")


class ConversationNotFoundError(Exception):
    """Raised when a conversation does not exist."""


class ConversationAccessDeniedError(Exception):
    """Raised when a user tries to access another user's conversation."""


def get_conversation(
    db: Session,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Conversation:
    """Get a conversation by ID with ownership check.

    Raises:
        ConversationNotFoundError: If the conversation doesn't exist.
        ConversationAccessDeniedError: If the user doesn't own it.
    """
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise ConversationNotFoundError("Conversation not found")
    if conv.user_id != user_id:
        raise ConversationAccessDeniedError("Access denied to this conversation")
    return conv


def list_conversations(
    db: Session,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Conversation], int]:
    """List conversations for a user with caching.

    Returns (conversations, total_count).
    """
    cache_key = conversation_list_key(user_id)
    cached = cache_service.get(cache_key)
    if cached is not None:
        cached_ids = cached.get("ids", [])
        cached_total = cached.get("total", 0)
        # Rehydrate from cached IDs
        convs = [db.query(Conversation).filter(Conversation.id == uid).first() for uid in cached_ids]
        convs = [c for c in convs if c is not None]
        if len(convs) == cached_total:
            return convs, cached_total

    total = db.query(Conversation).filter(Conversation.user_id == user_id).count()
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Cache full set of conversation IDs so any pagination still benefits
    all_convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    cache_service.set(
        cache_key,
        {
            "ids": [str(c.id) for c in all_convs],
            "total": len(all_convs),
        },
        ttl=settings.CACHE_CONVERSATION_TTL,
    )

    return conversations, total


def create_conversation(
    db: Session,
    user_id: uuid.UUID,
    title: Optional[str] = None,
) -> Conversation:
    """Create a new conversation.

    If no title is provided, a placeholder is used (the auto-title
    will be generated when the first message is sent).
    """
    conv_title = title or "New conversation"
    conv = Conversation(user_id=user_id, title=conv_title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    logger.info("conversation.created", conversation_id=str(conv.id), user_id=str(user_id))
    invalidate_conversation_cache(user_id)
    return conv


def update_conversation_title(
    db: Session,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    new_title: str,
) -> Conversation:
    """Update conversation title with ownership check."""
    conv = get_conversation(db, conversation_id, user_id)
    conv.title = new_title
    db.commit()
    db.refresh(conv)
    logger.info("conversation.renamed", conversation_id=str(conv.id), user_id=str(user_id))
    invalidate_conversation_cache(user_id)
    return conv


def delete_conversation(
    db: Session,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Delete a conversation and all its messages (cascade)."""
    conv = get_conversation(db, conversation_id, user_id)
    db.delete(conv)
    db.commit()
    logger.info("conversation.deleted", conversation_id=str(conversation_id), user_id=str(user_id))
    invalidate_conversation_cache(user_id)
    # Also invalidate message cache for this conversation
    invalidate_message_cache(conversation_id)


def auto_title_from_message(
    message_content: str,
    max_length: int = settings.AUTO_TITLE_LENGTH,
) -> str:
    """Generate a concise title from the first user message."""
    # Take the first line or first N characters
    first_line = message_content.split("\n")[0].strip()
    if len(first_line) <= max_length:
        return first_line
    return first_line[: max_length - 3] + "..."
