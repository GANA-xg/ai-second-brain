import enum
import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Enum, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class MessageRole(str, enum.Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageStatus(str, enum.Enum):
    """Track the status of an assistant message through its lifecycle."""

    PENDING = "PENDING"  # Saved before Gemini call
    COMPLETED = "COMPLETED"  # Gemini returned successfully
    FAILED = "FAILED"  # Gemini call failed
    CANCELLED = "CANCELLED"  # Client disconnected during streaming


class Message(BaseModel):
    __tablename__ = "messages"

    __table_args__ = (
        Index(
            "ix_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            name="message_role",
        ),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # ── Chat system extensions ────────────────────────────────────────

    status: Mapped[Optional[MessageStatus]] = mapped_column(
        Enum(
            MessageStatus,
            name="message_status",
            create_constraint=True,
        ),
        nullable=True,
        default=None,
        comment="Lifecycle status for ASSISTANT messages",
    )

    citations: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="Citation list from the RAG pipeline",
    )

    error_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="Error details if status == FAILED",
    )

    prompt_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )

    completion_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )

    total_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )

    # ── Relationships ─────────────────────────────────────────────────

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
    )
