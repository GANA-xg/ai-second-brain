"""ChunkEmbedding model — stores generated embeddings with version metadata.

Each chunk can have multiple embeddings over time as models are upgraded,
but only one embedding per (chunk_id, embedding_version) pair.
"""
import uuid

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chunk import Chunk


class ChunkEmbedding(BaseModel):
    __tablename__ = "chunk_embeddings"

    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "embedding_version",
            name="uq_chunk_embeddings_chunk_version",
        ),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    embedding: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )

    embedding_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    embedding_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    embedding_dimension: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Average logit / magnitude score (for quality filtering)
    magnitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    chunk: Mapped["Chunk"] = relationship(
        back_populates="embeddings",
    )
