import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from sqlalchemy import Enum
import enum


class FlashcardDifficulty(str, enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
class Flashcard(BaseModel):
    __tablename__ = "flashcards"

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