
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, Text
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chunk import Chunk

class FlashcardDifficulty(str, enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class Flashcard(BaseModel):
    __tablename__ = "flashcards"
    __table_args__ = (
        Index(
            "ix_flashcards_user_created",
            "user_id",
            "created_at",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    difficulty: Mapped[FlashcardDifficulty] = mapped_column(
        Enum(FlashcardDifficulty, name="flashcard_difficulty"),
        default=FlashcardDifficulty.MEDIUM,
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(
        back_populates="flashcards",
    )

    document: Mapped["Document"] = relationship(
        back_populates="flashcards",
    )

    source_chunk: Mapped["Chunk | None"] = relationship(
        back_populates="flashcards",
    )