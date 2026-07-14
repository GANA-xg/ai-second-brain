"""Memory model for user long-term memory storage.

Stores user preferences, goals, and facts extracted from conversations.
Supports soft-delete, active/inactive states, and confidence scoring.
"""

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum as SAEnum, Float, ForeignKey, String, Text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.message import Message


class MemoryType(str, enum.Enum):
    """Types of durable memories extracted from conversations."""
    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    GOAL = "GOAL"


class Memory(BaseModel):
    """A durable long-term memory extracted from a user's conversation."""

    __tablename__ = "memories"
    __table_args__ = (
        Index(
            "ix_memories_user_type",
            "user_id",
            "memory_type",
        ),
        UniqueConstraint(
            "user_id",
            "key",
            name="uq_memories_user_key",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Legacy key/value — kept for backward compatibility.
    # New code uses `content` instead of `value` and `key`.
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # New fields for the Part 10 memory system
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="The actual memory content (replaces key/value pattern)",
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Confidence score 0.0–1.0 from the extraction model",
    )

    source_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="The message that triggered this memory extraction",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Soft-active flag; inactive memories are excluded from prompts",
    )

    memory_type: Mapped[MemoryType] = mapped_column(
        SAEnum(MemoryType, name="memory_type"),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(
        back_populates="memories",
    )

    source_message: Mapped[Optional["Message"]] = relationship(
        foreign_keys=[source_message_id],
    )

    @property
    def is_deleted(self) -> bool:
        """Convenience: True if soft-deleted (deleted_at is set)."""
        return self.deleted_at is not None
