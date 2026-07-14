import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chunk_embedding import ChunkEmbedding
    from app.models.flashcard import Flashcard
    from app.models.quiz_question import QuizQuestion


class Chunk(BaseModel):
    __tablename__ = "chunks"

    __table_args__ = (
        Index(
            "ix_chunks_document_order",
            "document_id",
            "chunk_index",
        ),
        CheckConstraint(
            "chunk_index >= 0",
            name="ck_chunks_chunk_index_non_negative",
        ),
        CheckConstraint(
            "character_end > character_start",
            name="ck_chunks_character_range_valid",
        ),
        CheckConstraint(
            "token_estimate > 0",
            name="ck_chunks_token_estimate_positive",
        ),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    slide_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    section: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    character_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    character_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    token_estimate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    embedding_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )

    document: Mapped["Document"] = relationship(
        back_populates="chunks",
    )

    embeddings: Mapped[list["ChunkEmbedding"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )

    flashcards: Mapped[list["Flashcard"]] = relationship(
        back_populates="source_chunk",
        cascade="all, delete-orphan",
    )

    quiz_questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="source_chunk",
        cascade="all, delete-orphan",
    )