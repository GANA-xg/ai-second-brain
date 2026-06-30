import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


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
            "token_count > 0",
            name="ck_chunks_token_count_positive",
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

    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    embedding_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )

    document: Mapped["Document"] = relationship(
        back_populates="chunks",
    )