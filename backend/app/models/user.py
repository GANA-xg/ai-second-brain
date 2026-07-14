from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.document import Document
    from app.models.flashcard import Flashcard
    from app.models.memory import Memory
    from app.models.quiz import Quiz
    from app.models.quiz_attempt import QuizAttempt
    from app.models.refresh_token import RefreshToken
    from app.models.retrieval_trace import RetrievalTrace

class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    password_reset_token_hash: Mapped[str | None] = mapped_column(
        String(64),  # SHA-256 hex digest
        nullable=True,
        default=None,
    )

    password_reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    flashcards: Mapped[list["Flashcard"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    quizzes: Mapped[list["Quiz"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    memories: Mapped[list["Memory"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    retrieval_traces: Mapped[list["RetrievalTrace"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
